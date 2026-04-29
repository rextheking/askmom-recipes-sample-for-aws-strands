# Agent

The brain of AskMom Recipes. A Strands agent with a small set of tools that:

1. Extract ingredients from a photo and/or text.
2. Suggest healthy recipes given ingredients and dietary preferences.
3. Enrich each recipe with grounded nutrition and origin facts.
4. Format the results for the frontend.

## Layout

```
agent/
├── askmom/
│   ├── __init__.py
│   ├── agent.py          # Strands agent setup + entry points
│   ├── prompts.py        # System prompts
│   ├── models.py         # Pydantic-ish dataclasses for recipes, etc.
│   └── tools/
│       ├── __init__.py
│       ├── extract_ingredients.py
│       ├── suggest_recipes.py
│       ├── lookup_food_facts.py
│       ├── lookup_food_origin.py
│       └── format_recipe_card.py
├── tests/
│   └── test_smoke.py
├── local_run.py          # Run the agent end-to-end locally
├── requirements.txt
└── README.md
```

## Running locally

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Make sure AWS creds are set and Bedrock Claude Haiku is enabled in us-east-1.
cp ../.env.example ../.env
# Edit ../.env as needed.

python local_run.py
```

`local_run.py` runs the agent with a hardcoded ingredient list (no photo needed) so you can iterate on prompts fast.

## Tools

Each tool is a small, focused function exposed to the Strands agent:

| Tool | Job |
|---|---|
| `extract_ingredients_from_image` | Bedrock vision call on a photo, returns ingredient list |
| `extract_ingredients_from_text` | Normalize typed ingredients |
| `suggest_recipes` | LLM call, returns 3 healthy recipe candidates |
| `lookup_food_facts` | USDA FoodData Central API for nutrition |
| `lookup_food_origin` | Grounded origin/history lookup |
| `format_recipe_card` | Assemble final JSON for the frontend |

Keeping tools small and single-purpose is intentional. The blog walks through why.
