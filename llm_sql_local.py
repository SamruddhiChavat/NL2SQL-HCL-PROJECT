#llm_sql_local.py

import re
from flan_sql_local import FlanSQLLLM


class LocalLLM:
    def __init__(self, db_type="mssql"):
        self.db_type = db_type.lower()
        self.flan = FlanSQLLLM()

        self.schema_text = None
        self.schema_info = {}

    def set_schema(self, schema_text: str):
        self.schema_text = schema_text
        self.schema_info = {}

        table = None
        for line in schema_text.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("Table:"):
                table = line.split("Table:")[1].strip()
                self.schema_info[table] = []
                continue

            if line.startswith("-"):
                col = line.split()[1]
                self.schema_info[table].append(col)


    def detect_intent(self, question: str):
        q = question.lower()

        priority_intents = {
            "avg_delay": [
                "average delay",
                "avg delivery delay",
                "mean delay",
                "average late days"
            ],

            "late_orders": [
                "late orders",
                "orders delivered late",
                "delayed orders",
                "delayed delivery",
                "late delivery"
            ],

            "orders_per_payment": [
                "how many orders per payment type",
                "orders per payment",
                "payment orders count",
                "payment vs orders"
            ],

            "revenue": [
                "revenue",
                "payment revenue",
                "sales",
                "earnings",
                "payment analytics"
            ],

            "heavy_products": [
                "heavy",
                "weight",
                "grams",
                "> 500",
                "greater than"
            ],

            "top_sellers": [
                "top sellers",
                "best sellers",
                "most sellers"
            ],

            "customer_city": [
                "customer city",
                "customer cities"
            ],

            "seller_city": [
                "seller city",
                "seller cities"
            ],

            "reviews": [
                "reviews",
                "rating",
                "score"
            ],
        }

        for key, keywords in priority_intents.items():
            for k in keywords:
                if k in q:
                    return key

        if "products" in q:
            return "list_products"

        if "customers" in q:
            return "list_customers"

        if "orders" in q:
            return "list_orders"

        return "unknown"


    def template_sql(self, intent):
        templates = {
            "list_customers": "SELECT TOP 200 * FROM customers;",

            "list_products": "SELECT TOP 200 * FROM products;",

            "list_orders": "SELECT TOP 200 * FROM orders;",

            "delivered_orders": """
SELECT TOP 200 *
FROM orders
WHERE order_status = 'delivered'
ORDER BY order_purchase_timestamp DESC;
""",

            "customer_city": """
SELECT DISTINCT customer_city, customer_state
FROM customers
WHERE customer_city IS NOT NULL
ORDER BY customer_city;
""",

            "seller_city": """
SELECT DISTINCT seller_city, seller_state
FROM sellers
WHERE seller_city IS NOT NULL
ORDER BY seller_city;
""",

            "top_sellers": """
SELECT TOP 20 
    oi.seller_id,
    COUNT(DISTINCT oi.order_id) AS total_orders,
    COUNT(DISTINCT oi.product_id) AS total_products
FROM order_items oi
GROUP BY oi.seller_id
ORDER BY total_orders DESC;
""",

            "heavy_products": """
SELECT TOP 200 *
FROM products
WHERE product_weight_g IS NOT NULL
AND product_weight_g > 500
ORDER BY product_weight_g DESC;
""",

            "revenue": """
SELECT 
    p.payment_type,
    COUNT(*) AS total_orders,
    SUM(p.payment_value) AS total_revenue
FROM order_payments p
GROUP BY p.payment_type
ORDER BY total_revenue DESC;
""",

            "orders_per_payment": """
SELECT 
    p.payment_type,
    COUNT(*) AS total_orders
FROM order_payments p
GROUP BY p.payment_type
ORDER BY total_orders DESC;
""",

            "avg_delay": """
SELECT 
    AVG(DATEDIFF(
        day,
        o.order_estimated_delivery_date,
        o.order_delivered_customer_date
    )) AS avg_delay_days
FROM orders o
WHERE o.order_delivered_customer_date IS NOT NULL;
""",

            "late_orders": """
SELECT TOP 200
    o.order_id,
    o.order_status,
    o.order_estimated_delivery_date,
    o.order_delivered_customer_date
FROM orders o
WHERE o.order_delivered_customer_date IS NOT NULL
AND o.order_delivered_customer_date > o.order_estimated_delivery_date
ORDER BY o.order_delivered_customer_date DESC;
""",

            "reviews": """
SELECT TOP 200
    r.order_id,
    r.review_score,
    r.review_comment_title,
    r.review_comment_message
FROM order_reviews r
ORDER BY r.review_score ASC;
"""
        }

        return templates.get(intent, None)


    def clean_sql(self, sql: str):
        sql = sql.strip()

        if not sql.lower().startswith("select"):
            raise ValueError("Generated SQL is not a SELECT query")

        dangerous = ["drop", "delete", "truncate", "update", "insert"]
        for d in dangerous:
            if d in sql.lower():
                raise ValueError("Unsafe SQL detected")

        if not sql.endswith(";"):
            sql += ";"

        return sql


    def generate_sql(self, schema_text, question: str, result_limit=200):

        if self.schema_text != schema_text:
            self.set_schema(schema_text)

        intent = self.detect_intent(question)
        template = self.template_sql(intent)

        if template:
            return self.clean_sql(template)

        # LLM fallback
        prompt = f"""
You are a strict SQL Server query generator.
Generate ONE correct SQL query only.

Schema:
{schema_text}

Question: {question}
SQL:
"""
        raw = self.flan.generate(prompt)
        sql = self.clean_sql(raw)

        if "top" not in sql.lower():
            sql = sql.replace("SELECT", f"SELECT TOP {result_limit} ")

        return sql