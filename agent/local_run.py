"""Run the AskMom agent locally with hardcoded inputs.

Fast iteration loop for the agent and tools without any AWS infra beyond
Bedrock access.

Usage:
    cd ask_moms_recipe/agent
    python local_run.py                              # text-only sample
    python local_run.py --text "chicken, rice"       # custom text
    python local_run.py --refine <session_id> "make it quicker"
"""

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

# Load ../.env if present so AWS_REGION, BEDROCK_MODEL_ID, etc. are available.
load_dotenv(dotenv_path="../.env")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run AskMom agent locally.")
    parser.add_argument(
        "--text",
        default="chicken, spinach, lemon, rice, garlic, olive oil",
        help="Typed ingredients.",
    )
    parser.add_argument(
        "--preferences",
        default="low_sodium",
        choices=[
            "none",
            "vegetarian",
            "low_sodium",
            "diabetic_friendly",
            "gluten_free",
        ],
    )
    parser.add_argument("--photo-key", help="Optional S3 key of a grocery photo.")
    parser.add_argument(
        "--refine",
        nargs=2,
        metavar=("SESSION_ID", "INSTRUCTION"),
        help="Refine a previous session (in-memory only; same process run).",
    )
    args = parser.parse_args()

    # Import here so --help works even if strands isn't installed yet.
    from askmom.agent import ask, refine

    if args.refine:
        session_id, instruction = args.refine
        result = refine(session_id=session_id, instruction=instruction)
    else:
        print("AskMom Recipes — local run")
        print("-" * 40)
        print(f"Text: {args.text}")
        print(f"Preferences: {args.preferences}")
        if args.photo_key:
            print(f"Photo S3 key: {args.photo_key}")
        print()

        result = ask(
            photo_s3_key=args.photo_key,
            text_ingredients=args.text,
            preferences=args.preferences,
        )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
