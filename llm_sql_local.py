# llm_sql_local.py

import re
import difflib
from flan_sql_local import FlanSQLLLM


def fuzzy_contains(text, keywords):
    text = text.lower()
    for word in keywords:
        w = word.lower()
        if w in text:
            return True
        if difflib.SequenceMatcher(None, text, w).ratio() >= 0.80:
            return True
    return False


class LocalLLM:
    def __init__(self, db_type="mssql"):
        self.db_type = db_type.lower()
        self.flan = FlanSQLLLM()
        self.schema_text = None
        self.schema_info = {}
        self.all_columns = set()
        self.all_tables = set()

    # ---------------- SCHEMA ----------------
    def set_schema(self, schema_text: str):
        self.schema_text = schema_text
        self.schema_info = {}
        self.all_columns = set()
        self.all_tables = set()

        table = None
        for line in schema_text.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("Table:"):
                table = line.split("Table:")[1].strip()
                self.schema_info[table] = []
                self.all_tables.add(table)
                continue

            if line.startswith("-"):
                col = line.split()[1]
                self.schema_info[table].append(col)
                self.all_columns.add(col)

    # ensure ONLY valid TOP detection
    def extract_number(self, q):
        q = q.lower()

        # check for explicit "top X"
        m = re.search(r"top\s+(\d+)", q)
        if m:
            return int(m.group(1))

        # check "first X"
        m = re.search(r"first\s+(\d+)", q)
        if m:
            return int(m.group(1))

        return 200

    def detect_year(self, q):
        nums = re.findall(r"\b20\d{2}\b", q)
        return nums[0] if nums else None

    # ------------- INTENT ENGINE ----------------
    def detect_intent(self, question: str):
        q = question.lower()
        q = q.replace("statistics", "stats")
        q = q.replace("delivery", "delivered")

        # hard stop malicious stuff
        if any(x in q for x in ["drop", "truncate", "delete", "alter", "update"]):
            return "safe_mode"

        if fuzzy_contains(q, [
            "category revenue",
            "product category revenue",
            "category brings most revenue",
            "which category brings most revenue",
            "revenue by category",
            "category wise revenue"
        ]):
            return "category_revenue"

        if "expensive" in q and "product" in q:
            return "expensive_products"

        if "revenue" in q and "month" in q:
            return "monthly_revenue"

        if "revenue" in q and "state" in q:
            return "state_revenue"

        # city spend intent FIXED
        if fuzzy_contains(q, [
            "average spend city",
            "highest average spend",
            "customers spend highest",
            "top cities spend",
            "avg spend city",
            "cities where customers spend most",
            "highest spending cities"
        ]):
            return "avg_spend_city"

        late_month_patterns = [
            "late orders per month",
            "delivered late per month",
            "late delivered per month",
            "late deliveries per month",
            "late delivery stats",
            "late delivery per month",
            "how many orders were delivered late per month",
            "deliveries that were late per month"
        ]
        if fuzzy_contains(q, late_month_patterns):
            return "late_orders_monthly"

        if fuzzy_contains(q, ["late orders", "delivered late", "late delivered"]):
            return "late_orders"

        intents = {
            "avg_delay": ["average delay", "avg delay", "mean delay"],
            "orders_per_payment": ["orders per payment", "payment orders", "payment type count"],
            "revenue": ["revenue", "sales", "earnings", "payment revenue"],
            "order_trend": [
                "order trend",
                "orders over time",
                "order timeline",
                "order growth",
                "monthly trend",
                "orders monthly trend"
            ],
            "heavy_products": ["heavy", "weight", "grams", "kg"],
            "top_sellers": ["top sellers", "best sellers", "most sellers"],
            "customer_city": ["customer city", "customer cities"],
            "seller_city": ["seller city", "seller cities"],
            "customers_per_state": ["customers per state", "state wise customers"],
            "products_with_price": ["products with price", "product price"],
            "customer_orders": [
                "customer orders",
                "orders by customer",
                "customer with order",
                "customers with their orders",
                "customer order list"
            ],
            "worst_sellers": ["worst sellers", "bad sellers", "lowest rating", "worst performing sellers"],
            "seller_avg_review": ["seller average review", "seller review score", "seller rating"],
            "expensive_city": ["most expensive city", "highest price city"],
            "expensive_products": ["most expensive products", "top expensive products", "highest priced products"],
            "reviews": ["reviews", "rating", "review score"]
        }

        for k, keys in intents.items():
            if fuzzy_contains(q, keys):
                return k

        if fuzzy_contains(q, ["products", "prducts", "prodcts"]):
            return "list_products"
        if fuzzy_contains(q, ["customers", "costomers", "custmers"]):
            return "list_customers"
        if fuzzy_contains(q, ["orders", "odres", "ordrs"]):
            return "list_orders"

        return "unknown"

    # -------------- SQL TEMPLATE ----------------
    def template_sql(self, intent, question):
        n = self.extract_number(question)
        year = self.detect_year(question)

        if intent == "safe_mode":
            return "SELECT TOP 200 * FROM orders;"

        templates = {
            "list_customers": f"SELECT TOP {n} * FROM customers;",
            "list_products": f"SELECT TOP {n} * FROM products;",
            "list_orders": f"SELECT TOP {n} * FROM orders;",

            "customer_city":
"""
SELECT DISTINCT customer_city, customer_state
FROM customers
WHERE customer_city IS NOT NULL
ORDER BY customer_city;
""",

            "seller_city":
"""
SELECT DISTINCT seller_city, seller_state
FROM sellers
WHERE seller_city IS NOT NULL
ORDER BY seller_city;
""",

            "customers_per_state":
"""
SELECT customer_state, COUNT(*) AS total_customers
FROM customers
GROUP BY customer_state
ORDER BY total_customers DESC;
""",

            "heavy_products": f"""
SELECT TOP {n} *
FROM products
WHERE product_weight_g IS NOT NULL
AND product_weight_g > 500
ORDER BY product_weight_g DESC;
""",

            "top_sellers": f"""
SELECT TOP {n}
    oi.seller_id,
    COUNT(DISTINCT oi.order_id) AS total_orders
FROM order_items oi
GROUP BY oi.seller_id
ORDER BY total_orders DESC;
""",

            "orders_per_payment":
"""
SELECT payment_type, COUNT(*) AS total_orders
FROM order_payments
GROUP BY payment_type
ORDER BY total_orders DESC;
""",

            "revenue":
"""
SELECT payment_type, SUM(payment_value) AS total_revenue
FROM order_payments
GROUP BY payment_type
ORDER BY total_revenue DESC;
""",

            "monthly_revenue":
"""
SELECT FORMAT(TRY_CONVERT(datetime,o.order_purchase_timestamp),'yyyy-MM') AS month,
       SUM(p.payment_value) AS total_revenue
FROM orders o
JOIN order_payments p ON o.order_id = p.order_id
WHERE TRY_CONVERT(datetime,o.order_purchase_timestamp) IS NOT NULL
GROUP BY FORMAT(TRY_CONVERT(datetime,o.order_purchase_timestamp),'yyyy-MM')
ORDER BY month;
""",

            "state_revenue":
"""
SELECT c.customer_state,
       SUM(p.payment_value) AS total_revenue
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_payments p ON o.order_id = p.order_id
GROUP BY c.customer_state
ORDER BY total_revenue DESC;
""",

            "avg_spend_city":
"""
SELECT TOP 10
    c.customer_city,
    AVG( oi.price ) AS avg_spend
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY c.customer_city
ORDER BY avg_spend DESC;
""",

            "order_trend":
"""
SELECT FORMAT(TRY_CONVERT(datetime,order_purchase_timestamp),'yyyy-MM') AS month,
       COUNT(*) AS total_orders
FROM orders
WHERE TRY_CONVERT(datetime,order_purchase_timestamp) IS NOT NULL
GROUP BY FORMAT(TRY_CONVERT(datetime,order_purchase_timestamp),'yyyy-MM')
ORDER BY month;
""",

            "avg_delay":
"""
SELECT AVG(DATEDIFF(day, order_estimated_delivery_date, order_delivered_customer_date)) AS avg_delay_days
FROM orders
WHERE order_delivered_customer_date IS NOT NULL;
""",

            "late_orders":
f"""
SELECT 
    order_id,
    order_status,
    order_estimated_delivery_date,
    order_delivered_customer_date
FROM orders
WHERE order_delivered_customer_date IS NOT NULL
AND order_delivered_customer_date > order_estimated_delivery_date
{f"AND YEAR(order_delivered_customer_date) = {year}" if year else ""}
ORDER BY order_delivered_customer_date DESC;
""",

            "late_orders_monthly":
"""
SELECT FORMAT(TRY_CONVERT(datetime,order_delivered_customer_date),'yyyy-MM') AS month,
       COUNT(*) AS late_orders
FROM orders
WHERE order_delivered_customer_date IS NOT NULL
AND order_delivered_customer_date > order_estimated_delivery_date
GROUP BY FORMAT(TRY_CONVERT(datetime,order_delivered_customer_date),'yyyy-MM')
ORDER BY month;
""",

            "products_with_price": f"""
SELECT TOP {n}
    p.product_id,
    p.product_category_name,
    oi.price,
    oi.freight_value
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id;
""",

            "customer_orders": f"""
SELECT TOP {n}
    c.customer_id,
    c.customer_city,
    o.order_id,
    o.order_status
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id;
""",

            "worst_sellers": f"""
SELECT TOP {n}
    oi.seller_id,
    AVG(r.review_score) AS avg_review_score
FROM order_reviews r
JOIN order_items oi ON r.order_id = oi.order_id
GROUP BY oi.seller_id
ORDER BY avg_review_score ASC;
""",

            "seller_avg_review": f"""
SELECT TOP {n}
    oi.seller_id,
    AVG(r.review_score) AS avg_review_score
FROM order_reviews r
JOIN order_items oi ON r.order_id = oi.order_id
GROUP BY oi.seller_id
ORDER BY avg_review_score DESC;
""",

            "category_revenue":
"""
SELECT pr.product_category_name,
       SUM(oi.price) AS total_revenue
FROM order_items oi
JOIN products pr ON oi.product_id = pr.product_id
GROUP BY pr.product_category_name
ORDER BY total_revenue DESC;
""",

            "expensive_city": f"""
SELECT TOP {n}
    c.customer_city,
    AVG(oi.price) AS avg_spent
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY c.customer_city
ORDER BY avg_spent DESC;
""",

            "expensive_products": f"""
SELECT TOP {n}
    p.product_id,
    p.product_category_name,
    oi.price
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
ORDER BY oi.price DESC;
""",

            "reviews": f"""
SELECT TOP {n}
    order_id,
    review_score,
    review_comment_title,
    review_comment_message
FROM order_reviews
ORDER BY review_score ASC;
"""
        }

        return templates.get(intent, None)

    # ------------- SAFETY ----------------
    def clean_sql(self, sql: str):
        sql = sql.strip()
        if not sql.lower().startswith("select"):
            raise ValueError("Generated SQL is not a SELECT query")

        banned = ["drop", "delete", "truncate", "insert", "update", "alter"]
        for b in banned:
            if b in sql.lower():
                raise ValueError("Unsafe SQL detected")

        if not sql.endswith(";"):
            sql += ";"
        return sql

    # ------------- MAIN ----------------
    def generate_sql(self, schema_text, question: str, result_limit=200):
        if self.schema_text != schema_text:
            self.set_schema(schema_text)

        intent = self.detect_intent(question)
        template = self.template_sql(intent, question)

        if template:
            return self.clean_sql(template)

        prompt = f"""
You are a STRICT SQL Server query generator.
RULES:
- Output ONLY ONE SQL query
- MUST be SELECT only
- MUST use ONLY existing tables/columns
- NO explanation text

Schema:
{schema_text}

User Question: {question}

SQL:
"""
        raw = self.flan.generate(prompt)
        sql = self.clean_sql(raw)

        if "top" not in sql.lower():
            sql = sql.replace("SELECT", f"SELECT TOP {result_limit} ")

        return sql
