"""
Checks the diagram-reading step against the labelled examples in data/.

For each example it sends the diagram image (and the parts table, when there is one) to the model and compares
the bearing codes it returns with label.json. Nothing is looked up on the web.

Run from the repository root, with ANTHROPIC_API_KEY set:  python -m scripts.eval_extraction
Each example is one paid model request.
"""
import json
from pathlib import Path

from app.backend.llm.client import USAGE, estimated_cost
from app.backend.llm.logic import extract_from_documents

DATA = Path("data")
NOT_BEARINGS = {"spacer", "axle"}


def norm(code: str) -> str:
    # labels leave out the fill marking, diagrams often print it: '6902 2RS MAX' is the labelled '6902 2RS'
    return " ".join(t for t in code.upper().split() if t not in {"MAX", "FILL"})


def main() -> None:
    perfect = 0
    examples = sorted(p.parent for p in DATA.glob("*/ex-*/label.json"))
    for ex in examples:
        label = json.loads((ex / "label.json").read_text())
        want_codes = {norm(x) for a in label.values() for x in a["sequence"] if x not in NOT_BEARINGS}

        documents = [(f.read_bytes(), "image/png") for f in (ex / "diagram.png", ex / "table.png") if f.exists()]
        got = extract_from_documents(documents)
        got_codes = {norm(b.code) for b in got.bearings}

        ok = got_codes == want_codes
        perfect += ok
        print(f"\n{ex}  {'OK' if ok else 'DIFFERENT'}")
        print(f"  codes     expected {sorted(want_codes)}")
        print(f"            got      {sorted(got_codes)}")
        if got.unresolved_references:
            print(f"            unresolved: {[r.description for r in got.unresolved_references]}")
    print(f"\n{perfect} of {len(examples)} examples match their label exactly")
    print(f"{USAGE['requests']} requests, {USAGE['input_tokens']} input and {USAGE['output_tokens']} output tokens, "
          f"about ${estimated_cost():.2f}")


if __name__ == "__main__":
    main()
