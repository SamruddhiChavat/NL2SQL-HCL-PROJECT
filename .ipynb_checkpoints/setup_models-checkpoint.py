# setup_models.py
"""
Ensure required Ollama models (mistral, llama3, phi) are available locally.
Run after cloning:
    python setup_models.py
"""

import sys

try:
    import ollama
except ImportError:
    print("The 'ollama' Python package is not installed.")
    print("Install it with: pip install ollama")
    sys.exit(1)

REQUIRED_MODELS = ["mistral", "llama3", "phi"]


def list_installed_models():
    """Return a set of installed base model names in Ollama."""
    try:
        data = ollama.list()
    except Exception as e:
        print(f"Error communicating with Ollama. Is the Ollama server running?\n{e}")
        sys.exit(1)

    models = data.get("models", [])
    names = set()
    for m in models:
        name = m.get("name", "")
        if not name:
            continue
        base = name.split(":")[0]
        names.add(base)
    return names


def ensure_models():
    installed = list_installed_models()
    print(f"Installed base models: {sorted(installed)}")

    for model_name in REQUIRED_MODELS:
        base = model_name
        if base in installed:
            print(f"Model '{model_name}' already installed.")
            continue

        print(f"Pulling model '{model_name}' via Ollama...")
        try:
            ollama.pull(model_name)
            print(f"Successfully pulled '{model_name}'.")
        except Exception as e:
            print(f"Failed to pull '{model_name}'. Error:\n{e}")
            print("Make sure Ollama is running and you have internet.")
            sys.exit(1)


def quick_prediction_demo():
    """Run one test prediction for each model."""
    tests = [
        ("mistral", "State the purpose of this project in one short sentence."),
        ("llama3", "State the purpose of this project in one short sentence."),
        ("phi", "State the purpose of this project in one short sentence."),
    ]
    for model, prompt in tests:
        try:
            print(f"\nTesting model '{model}'...")
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp["message"]["content"].strip()
            print("Model response:")
            print(content)
        except Exception as e:
            print(f"Test prediction for '{model}' failed. Error:\n{e}")


if __name__ == "__main__":
    print("Checking required models (mistral, llama3, phi)...")
    ensure_models()
    quick_prediction_demo()
    print("Setup complete.")
