"""
Writes the instructions the rule engine produces for one example of every kind of arrangement, so that the rules
can be read and checked by someone who knows the tool. No model is called.

Run from the repository root:  python -m scripts.sample_instructions
"""
from pathlib import Path

from app.backend.rules.engine import ArrangementSpec, BearingSpec, instructions_for, tools_for

OUT = Path("data/rules/SAMPLE_INSTRUCTIONS.txt")

b6902 = BearingSpec("6902 2RS", 15, 28, 7)
b6900 = BearingSpec("6900 2RS", 10, 22, 6)
b61801 = BearingSpec("61801 2RSR", 12, 21, 5)
b61803 = BearingSpec("61803 2RSR", 17, 26, 5)
b61804 = BearingSpec("61804 2RSR", 20, 32, 7)
BSB = dict(has_spacer=True, spacer_len_ge_10mm=True, spacer_mobility="moves")

SAMPLES = [
    ArrangementSpec("Simple pivot, alloy", "SP", "frame", "alloy", [[b6900]]),
    ArrangementSpec("Double stacked pivot, alloy", "SP", "frame", "alloy", [[b6902, b6902]]),
    ArrangementSpec("BSB pivot with a thin spacer ring, alloy", "BSB", "frame", "alloy", [[b61801], [b61801]],
                    has_spacer=True, spacer_len_ge_10mm=False),
    ArrangementSpec("BSB frame, spacer moves, carbon", "BSB", "frame", "carbon", [[b6902], [b6902]], **BSB),
    ArrangementSpec("BSB frame, spacer stuck, one side double-stacked, alloy", "BSB", "frame", "alloy",
                    [[b61803], [b61803, b61803]], has_spacer=True, spacer_len_ge_10mm=True, spacer_mobility="stuck"),
    ArrangementSpec("BSB hub, centre-lock", "BSB", "hub", "alloy", [[b6902], [b61804]], has_center_lock=True, **BSB),
    ArrangementSpec("BSB hub without spacer, 6-bolt", "BSB", "hub", "alloy", [[b6902], [b6902]],
                    has_center_lock=False, has_spacer=False),
    ArrangementSpec("Over-axle hub, 6-bolt", "OA", "hub", "alloy", [[b61804], [b61804]], has_center_lock=False,
                    axle_length="long"),
    ArrangementSpec("Over-axle frame main pivot, carbon", "OA", "frame", "carbon", [[b61804], [b61804]],
                    axle_length="long"),
    ArrangementSpec("Over-axle short, frame, alloy", "OA", "frame", "alloy", [[b6902], [b6902]], axle_length="short"),
    ArrangementSpec("BSB freehub, HG", "BSB", "freehub", "alloy", [[b6902], [b6902]],
                    freehub_body="hg_microspline", freehub_one_side=False, **BSB),
    ArrangementSpec("BSB freehub, both bearings from one side, XD", "BSB", "freehub", "alloy", [[b6902], [b6902]],
                    freehub_body="xd_xdr", freehub_one_side=True, **BSB),
]


def main() -> None:
    text = "\n\n".join(instructions_for(tools_for(spec)) for spec in SAMPLES)
    OUT.write_text(text + "\n")
    print(f"wrote {OUT} ({len(SAMPLES)} arrangements, {len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
