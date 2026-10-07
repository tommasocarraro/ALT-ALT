"""
Source of truth for the ALT/ALT press-configuration rules.

Every rule says which tool pieces are needed to REMOVE or INSTALL one bearing of one arrangement.
Rules were transcribed from the instructional diagrams on altalt.ca (data/altalt_site/instructions),
each of which was read both as text and as an image, then corrected with the tool owner's answers.
A rule with status "inferred" would have neither a diagram nor a confirmation behind it; none do at present.

Run `python3 data/rules/build_rules.py` to regenerate rules.json and RULES.md next to this file.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------------------------------
PIECES = {
    "stud": "Stud",
    "nut": "Standard Nut",
    "stud_stop": "Stud Stop",
    "handle": "Handle",
    "o_ring": "O-ring",
    "drift_re": "Drift RE",
    "pilot_short": "Pilot Short",
    "pilot_long": "Pilot Long",
    "step": "Step",
    "sleeve": "Sleeve",
    "sleeve_6": "Sleeve 6",
    "sleeve_long": "Sleeve Long",
    "stop_ctr": "Stop CTR",
    "stop_oal": "Stop OAL",
    "spacer_tube": "Spacer Tube",
    "alt_drift": "ALT Drift",
    "alt_rod": "ALT Rod",
    "alt_extractor": "ALT Extractor",
    "oa_drift": "Over Axle Drift",
}

# how the size of a piece is chosen
SIZES = {
    "od": "bearing OD",
    ">id": "smallest size larger than the bearing ID",
    "od_other": "OD of the bearing it rests against",
    ">seat": "larger than the bearing seat, so it rests on the part",
    "fits_bore": "largest OD that fits into the empty bore",
    "id": "bearing ID",
    "axle_id": "fits inside the axle",
    ">axle_id": "larger than the axle ID, so it pushes on the axle end",
    "axle_end": "rests on the end of the axle",
    "axle_od x od": "axle OD x bearing OD",
}

# sizes that exist in the catalogue, used by the rule engine to pick or to flag "not available"
AVAILABLE_SIZES = {
    "drift_re": [16, 19, 21, 22, 24, 26, 28, 30, 32, 35, 37, 41],
    "sleeve": [16, 19, 22, 24, 26, 28, 30, 32, 35, 37],
    "pilot_short": [10, 11, 12, 15, 17, 18, 20, 23, 25],
    "pilot_long": [10, 11, 12, 15, 17, 18, 20, 25],
    "alt_drift": [15, 17, 18, 20, 25],
    "alt_extractor": [10, 12, 15, 17, 18, 20, 25],
    "oa_drift": ["15x24", "15x26", "15x28", "15x30", "15x32", "17x26", "17x28", "17x30", "17x35",
                 "18x30", "18x32", "20x32", "20x37", "25x37"],
    "stud": [120, 180, 240],
}

GENERAL_NOTES = [
    "Every configuration is built on one Stud with a fastener at each end, except the ALT Extractor, "
    "which has its own built-in rod.",
    "Stud length (120, 180 or 240 mm) depends on the component and the number of pieces stacked on it; "
    "it is chosen by a person with the part in hand, not by a rule.",
    "Removal: the Drift RE pushes on the inner ring. Take the smallest Drift RE that is larger than the bearing ID.",
    "Install: take the Drift RE that matches the bearing OD. Which face presses follows the manufacturer: the "
    "flat side by default; the relief side when the bearing has to be slightly loaded, so that the drift "
    "presses only the outer ring in while the axle holds the inner ring from the other side, which takes "
    "the play out of the bearing.",
    "The Pilot sits inside the bearing, on the Stud, and keeps the drift centred on the bearing. "
    "Bearing ID 8 or 9 mm needs no Pilot: the Stud centres the tool.",
    "Pilots 10, 11 and 12 are for centring only, never for pressing.",
    "The Pilot Long exists to keep the inner spacer aligned with the bearings while the second bearing goes in.",
    "A Sleeve (with its Step) is a leverage piece with room inside it: it is needed wherever something has to "
    "travel past the leverage surface (the bearing on removal; a pilot, an axle or an inner ring on install).",
    "An Over Axle Drift is a press piece with room inside it: it is needed wherever an axle (or a pilot) "
    "sticks out of the bearing being pressed. It is always pushed by a Drift RE, never by a nut.",
    "Over Axle Drifts are sold as one long and one short per size; the long one is for the driver side, "
    "where the axle sticks out further. Sizes with ID 18, 20 and 25 only come short.",
    "Drift RE 41 is the leverage drift for 37 mm bearings. There is no Sleeve for 21 mm bearings.",
    "Sleeve 6 rests on a 6-bolt disc mount. Sleeve Long centres and rests on a centre-lock disc mount "
    "(disc removed). Stop OAL rests on the drive side of a hub and clears a long axle end; it also fits "
    "the outboard end of XD/XDR freehubs.",
    "Material: acetal against carbon or delicate surfaces; aluminium for thin leverage surfaces, "
    "corroded, wide or double-stacked bearings, and shop use.",
    "A Stud Stop may only sit against a piece larger than 20 mm, and is never the fastener that is turned.",
    "The Handle can replace a Standard Nut.",
]

OPEN_QUESTIONS = [
    "Open-bore hub, install of the 1st bearing: the diagram shows a Pilot Long. No reason is given; "
    "a Pilot Short may do.",
    "O-ring quantities are counted from the drawings.",
]


def p(piece, size=None, qty=1, note=None):
    d = {"piece": piece, "qty": qty}
    if size:
        d["size"] = size
    if note:
        d["note"] = note
    return d


def opt(pieces, when=None, cond=None):
    """
    One way of filling a role. Several options in a role means: pick the one whose `when` applies.
    `when` is for people; `cond` is the same condition for the rule engine:
      six_bolt / center_lock   hub disc mount          hg / xd   freehub body
      frame                    the part is a frame     default   use this unless a more specific option applies
      manual                   only a person can tell (clearance, manufacturer's instructions): offered, never picked
    """
    return {"when": when, "cond": cond, "pieces": pieces}


def one(*pieces):
    return [opt(list(pieces))]


def op(id, operation, bearing, diagram, press, center, leverage, extras=None, hardware=None,
       side=None, notes=None, status="diagram", title=None, variant=None, when=None):
    return {
        "id": id,
        "title": title,
        "operation": operation,          # remove | install
        "bearing": bearing,              # single | 1st | 2nd | both
        "side": side,                    # disc | drive | None
        "variant": variant,              # set when the same job has two tool set-ups
        "when": when,                    # condition that selects this variant
        "status": status,                # diagram | confirmed | inferred
        "diagram": diagram,
        "press": press,
        "center": center,
        "leverage": leverage,
        "extras": extras or [],
        "hardware": hardware or HW_TWO,
        "notes": notes or [],
    }


# ---------------------------------------------------------------------------------------------------
# Building blocks shared by several diagrams
# ---------------------------------------------------------------------------------------------------
STEP, SLEEVE = p("step"), p("sleeve", "od")
ORING = p("o_ring")

HW_TWO = {"pieces": [p("stud"), p("nut", qty=2)],
          "note": "A Stud Stop may replace either nut if it sits against a piece larger than 20 mm."}
HW_TUBE = {"pieces": [p("stud"), p("nut", qty=2)],
           "note": "The nut on the Spacer Tube side must be a nut (not a Stud Stop). "
                   "A Stud Stop may replace the nut on the leverage side."}
HW_ALT = {"pieces": [p("stud"), p("nut")],
          "note": "ALT Drift: the ALT Rod threads onto the Stud and is the only part that is turned. "
                  "The single fastener on the leverage side may be a nut, Stud Stop or Handle and must not turn."}
HW_EXT = {"pieces": [p("nut")],
          "note": "ALT Extractor: it has its own built-in rod, so no Stud. "
                  "The fastener is a Standard Nut or a Stud Stop."}

LEV_STEP_SLEEVE = one(STEP, SLEEVE)
LEV_DISC = [opt([STEP, p("sleeve_6")], "6-bolt disc mount", "six_bolt"),
            opt([STEP, p("sleeve_long")], "centre-lock disc mount (disc removed)", "center_lock")]
LEV_FREEHUB = [opt([STEP, SLEEVE], "HG or Microspline freehub", "hg"),
               opt([p("stop_oal")], "XD or XDR freehub", "xd")]
LEV_FIRST_BEARING = opt([p("drift_re", "od_other", note="rests against the 1st bearing")],
                        "if the manufacturer asks to leverage against the 1st bearing", "manual")

ALT_DRIFT_WHEN = "spacer moves at least 1 mm off-axis AND spacer is at least 10 mm long AND bearing ID is 15/17/18/20/25"
ALT_EXT_WHEN = "spacer does not move, or is shorter than 10 mm, or bearing ID is 10/12"
ALT_NOTE = ("ALT Drift: it goes in from the far side, through the other bearing and the spacer, and pushes the "
            "inner ring from behind. If the Pilot does not fit the bearing ID, stop.")

PRESS_OUT = one(p("drift_re", ">id", note="pushes the inner ring"))
PRESS_IN = one(p("drift_re", "od", note="flat side on the bearing, unless the manufacturer asks for the relief side"))
OA_PAIR = [p("oa_drift", "axle_od x od"), p("drift_re", "od", note="pushes on the open end of the Over Axle Drift")]
OA_NOTE = "Never push on an Over Axle Drift with a nut, Stud Stop or Handle: always put a Drift RE behind it."
OA_SIDE_NOTE = ("Flat side of the Over Axle Drift presses both rings, relief side presses the outer ring only: "
                "follow the hub manufacturer.")
OA_ID_NOTE = "The bearing ID can be larger than the axle OD where the drift slides: size the drift to the axle."
CIRCLIP_NOTE = ("The arrangement picture shows a circlip between the bearings, but no diagram shows it: "
                "check for circlips before pressing.")
AXLE_PILOTS = one(p("pilot_long", "axle_id", note="in one end of the axle"),
                  p("pilot_short", "axle_id", note="in the other end of the axle"))


def remove_first(diagram, leverage, mode="bsb", side=None, status="diagram"):
    """The first bearing of a pair cannot be reached from behind: ALT Drift or ALT Extractor.
    mode: 'bsb' = long spacer, 'thin' = thin spacer ring or stacked bearings, 'none' = no spacer."""
    sfx = f"_{side}" if side else ""
    drift = op("remove_1st" + sfx, "remove", "1st", diagram, one(p("alt_drift", "id"), p("alt_rod")),
               one(p("pilot_short", "id")), leverage, [ORING], HW_ALT, side=side, notes=[ALT_NOTE],
               status=status, variant="ALT Drift",
               when=ALT_DRIFT_WHEN if mode == "bsb" else "bearing ID is 15/17/18/20/25")
    ext = op("remove_1st_extractor" + sfx, "remove", "1st", None, one(p("alt_extractor", "id")), [],
             LEV_STEP_SLEEVE, [], HW_EXT, side=side, status="confirmed", variant="ALT Extractor",
             when={"bsb": ALT_EXT_WHEN, "thin": None, "none": "bearing ID is 10/12, or preferred"}[mode],
             notes=["ALT Extractor: it grips the bearing from the front, so nothing has to reach behind it. "
                    "No diagram exists; the piece list was confirmed by the tool's owner."])
    return [ext] if mode == "thin" else [drift, ext]


# ---------------------------------------------------------------------------------------------------
# Operations per family of arrangement
# ---------------------------------------------------------------------------------------------------
def single_pivot_ops(prefix="", status="diagram", which="single"):
    return [
        op(prefix + "remove", "remove", which, "2SBP-R.pdf", PRESS_OUT,
           one(p("pilot_short", "id")), LEV_STEP_SLEEVE, [ORING], status=status),
        op(prefix + "install", "install", which, "2SBP-I.pdf", PRESS_IN,
           one(p("pilot_short", "id")),
           [opt([p("drift_re", ">seat", note="relief side gives 3 mm of room")], "default", "default"),
            opt([STEP, SLEEVE], "if the pilot or the inner ring would touch the leverage drift before the "
                                "bearing is home", "manual")],
           [ORING], status=status),
    ]


def double_stacked_ops():
    second = single_pivot_ops("2nd_", "confirmed", "2nd")
    first_install = single_pivot_ops("1st_", "confirmed", "1st")[1]
    return remove_first(None, LEV_STEP_SLEEVE, mode="thin") + [second[0], first_install, second[1]]


def bsb_suspension_ops(thin_spacer=False):
    centre_2nd = one(p("pilot_short", "id"), p("pilot_long", "id", note="sits in the 1st bearing and aligns the spacer"))
    if thin_spacer:
        centre_2nd = [opt(centre_2nd[0]["pieces"], "if the thin spacer ring can ride on the Pilot Long", "manual"),
                      opt([p("pilot_short", "id")], "otherwise: the spacer is too thin for a Pilot Long, align it by hand",
                          "default")]
    return remove_first("2BSB-R1.pdf", LEV_STEP_SLEEVE, mode="thin" if thin_spacer else "bsb") + [
        op("remove_2nd", "remove", "2nd", "2BSB-R2.pdf", PRESS_OUT, one(p("pilot_short", "id")),
           LEV_STEP_SLEEVE, [ORING, p("spacer_tube", note="reaches through the part to the drift")], HW_TUBE),
        op("install_1st", "install", "1st", "2BSB-I1.pdf", PRESS_IN, one(p("pilot_short", "id")),
           one(p("stop_ctr", note="leverages and centres in the opposite, empty seat")), [ORING]),
        op("install_2nd", "install", "2nd", "2BSB-I2.pdf", PRESS_IN, centre_2nd,
           one(p("drift_re", "od_other", note="rests against the 1st bearing")), [p("o_ring", qty=2)],
           status="confirmed" if thin_spacer else "diagram"),
    ]


def hub_remove_second(st):
    return [
        op("remove_2nd_disc", "remove", "2nd", "2HUB-OAOB-R2-Disc.pdf", PRESS_OUT, one(p("pilot_short", "id")),
           LEV_DISC, [ORING, p("spacer_tube", note="reaches through the hub to the drift")], HW_TUBE,
           side="disc", status=st),
        op("remove_2nd_drive", "remove", "2nd", "2HUB-OAOB-R2-Drive.pdf", PRESS_OUT, one(p("pilot_short", "id")),
           [opt([STEP, p("sleeve_6")], cond="default"), opt([p("stop_oal")], "alternative", "manual")],
           [ORING, p("spacer_tube", note="reaches through the hub to the drift")], HW_TUBE,
           side="drive", status=st),
    ]


def hub_install_first(st):
    return [
        op("install_1st_disc", "install", "1st", "2HUB-OAOB-I1-Disc.pdf", PRESS_IN, one(p("pilot_long", "id")),
           one(p("stop_ctr", note="in the drive-side seat")), [ORING], side="disc", status=st),
        op("install_1st_drive", "install", "1st", "2HUB-OAOB-I1-Drive.pdf", PRESS_IN, one(p("pilot_long", "id")),
           one(p("stop_ctr", note="in the disc-side seat")), [ORING], side="drive", status=st),
    ]


def bsb_hub_ops(no_spacer=False):
    st = "confirmed" if no_spacer else "diagram"
    mode = "none" if no_spacer else "bsb"
    if no_spacer:
        centre_2nd = one(p("pilot_short", "id"))
        both = op("install_both", "install", "both", None,
                  one(p("drift_re", "od", qty=2, note="one per bearing, pushes the outer ring")),
                  one(p("pilot_short", "id", qty=2, note="one per bearing")),
                  [opt([], "the two bearings are pressed against each other; no leverage piece", "default")],
                  [p("o_ring", qty=2)], status=st)
    else:
        centre_2nd = one(p("pilot_short", "id"),
                         p("pilot_long", "id", note="sits in the 1st bearing and aligns the spacer"))
        both = op("install_both", "install", "both", "2HUB-OB-IB.pdf",
                  one(p("drift_re", "od", note="disc side, pushes the outer ring"),
                      p("oa_drift", "od", note="drive side, pushes the outer ring; hollow, so the pilots can stick out"),
                      p("drift_re", "od", note="pushes on the Over Axle Drift")),
                  one(p("pilot_short", "id", note="disc-side bearing"),
                      p("pilot_long", "id", note="drive-side bearing and spacer"),
                      p("pilot_short", note="an extra, smaller one that helps the long pilot catch bearing and spacer")),
                  [opt([], "the two bearings are pressed against each other; no leverage piece", "default")],
                  [p("o_ring", qty=3)], notes=[OA_NOTE], status=st)
    return (
        remove_first("2HUB-OB-R1-Disc.pdf", LEV_DISC, mode, "disc", st)
        + remove_first("2HUB-OB-R1-Drive.pdf", one(STEP, p("sleeve_6")), mode, "drive", st)
        + hub_remove_second(st) + hub_install_first(st) + [
            op("install_2nd_disc", "install", "2nd", "2HUB-OB-I2-Disc.pdf", PRESS_IN, centre_2nd,
               [opt([p("stop_ctr", note="on the drive side")], "default", "default"), LEV_FIRST_BEARING],
               [p("o_ring", qty=3)], side="disc", status=st),
            op("install_2nd_drive", "install", "2nd", "2HUB-OB-I2-Drive.pdf", PRESS_IN, centre_2nd,
               LEV_DISC + [LEV_FIRST_BEARING], [p("o_ring", qty=3)], side="drive", status=st),
            both,
        ])


def over_axle_ops():
    st = "diagram"
    return [
        op("remove_1st_disc", "remove", "1st", "2HUB-OA-R1-Disc.pdf",
           one(p("drift_re", "axle_end", note="pushes the axle, which carries the disc-side bearing out")),
           AXLE_PILOTS, LEV_DISC, [p("o_ring", qty=3)], side="disc", status=st,
           title="Remove 1st bearing and axle, towards the disc side"),
        op("remove_1st_drive", "remove", "1st", "2HUB-OA-R1-Drive.pdf",
           one(p("drift_re", "axle_end", note="pushes the axle, which carries the drive-side bearing out")),
           AXLE_PILOTS, one(p("stop_oal")), [p("o_ring", qty=3)], side="drive", status=st,
           title="Remove 1st bearing and axle, towards the drive side"),
    ] + hub_remove_second(st) + hub_install_first(st) + [
        op("install_1st_drive_bore", "install", "1st", "2HUB-OA-I1-Drive-Bore.pdf", one(*OA_PAIR), AXLE_PILOTS,
           one(p("oa_drift", "fits_bore", note="the short one, seated in the empty disc-side bearing seat, "
                                               "ID = axle OD; relief side towards the axle shoulder"),
               p("drift_re", note="behind the leverage Over Axle Drift")),
           [p("o_ring", qty=4)], side="drive", status=st, notes=[OA_NOTE, OA_SIDE_NOTE],
           title="Install 1st bearing over the axle, drive side, leveraging in the empty seat"),
        op("install_2nd_disc", "install", "2nd", "2HUB-OA-I2-Disc.pdf", one(*OA_PAIR), AXLE_PILOTS,
           one(p("stop_oal", note="on the drive side, clears the axle end")), [p("o_ring", qty=4)],
           side="disc", status=st, notes=[OA_NOTE]),
        op("install_2nd_disc_bearing", "install", "2nd", "2HUB-OA-I2-Disc-Bearing.pdf", one(*OA_PAIR), AXLE_PILOTS,
           one(p("oa_drift", "axle_od x od", note="the long one, against the installed drive-side bearing"),
               p("drift_re", "od", note="behind the leverage Over Axle Drift")),
           [p("o_ring", qty=4)], side="disc", status=st, notes=[OA_NOTE, OA_SIDE_NOTE],
           title="Install 2nd bearing, disc side, leveraging against the 1st bearing"),
        op("install_2nd_drive", "install", "2nd", "2HUB-OA-I2-Drive.pdf", one(*OA_PAIR), AXLE_PILOTS,
           LEV_DISC + [opt([STEP, SLEEVE], "frame main pivot", "frame")],
           [p("o_ring", qty=4)], side="drive", status=st,
           notes=[OA_NOTE, OA_ID_NOTE, "The sleeve is there because the axle end sticks out of the 1st bearing."]),
        op("install_both", "install", "both", "2HUB-OA-IB.pdf",
           one(p("oa_drift", "axle_od x od", qty=2, note="one per bearing"),
               p("drift_re", "od", qty=2, note="one behind each Over Axle Drift")),
           AXLE_PILOTS, [opt([], "the two bearings are pressed against each other; no leverage piece", "default")],
           [p("o_ring", qty=4)], status=st, notes=[OA_NOTE, OA_ID_NOTE]),
    ]


def over_axle_short_ops():
    """Described by the tool's owner: the axle enters the bearings but does not stick out of them,
    so no Over Axle Drift is needed. Not drawn on altalt.ca."""
    st = "confirmed"
    push = one(p("pilot_short", ">axle_id", note="pushes the axle, which carries the far bearing out"))
    return [
        op("remove_1st_disc", "remove", "1st", None, push, [], LEV_DISC, [ORING], side="disc", status=st,
           title="Remove 1st bearing and axle, towards the disc side"),
        op("remove_1st_drive", "remove", "1st", None, push, [], one(STEP, p("sleeve_6")), [ORING],
           side="drive", status=st, title="Remove 1st bearing and axle, towards the drive side"),
    ] + hub_remove_second(st) + hub_install_first(st) + [
        op("install_2nd", "install", "2nd", None,
           one(p("drift_re", "od", note="pushes the outer ring; relief side towards the bearing so the pilot "
                                        "has room to back out")),
           one(p("pilot_short", "id", note="centres the bearing; the axle pushes it out as the bearing goes on"),
               p("pilot_short", "axle_id", note="centres the axle")),
           one(p("drift_re", "od_other", note="rests against the 1st bearing")), [p("o_ring", qty=2)],
           status=st, title="Install 2nd bearing onto the axle",
           notes=["Two pilots of different diameters: one for the bearing ID, one for the axle ID."]),
    ]


def freehub_each_side_ops():
    return remove_first("2Free-Each-R1.pdf", LEV_STEP_SLEEVE) + [
        op("remove_2nd", "remove", "2nd", "2Free-Each-R2.pdf", PRESS_OUT, one(p("pilot_short", "id")),
           LEV_FREEHUB + [opt([p("drift_re", ">seat")], "optional, if the bearing has room to come out", "manual")],
           [ORING, p("spacer_tube", note="reaches through the freehub to the drift")], HW_TUBE),
        op("install_1st", "install", "1st", "2Free-Each-I1.pdf", PRESS_IN, one(p("pilot_short", "id")),
           one(p("stop_ctr", note="leverages and centres on the opposite end")), [ORING]),
        op("install_2nd", "install", "2nd", "2Free-Each-I2.pdf", PRESS_IN,
           one(p("pilot_short", "id"), p("pilot_long", "id", note="sits in the 1st bearing and aligns the spacer")),
           one(p("drift_re", "od_other", note="rests against the 1st bearing")), [p("o_ring", qty=3)]),
    ]


def freehub_one_side_ops():
    extender = p("spacer_tube", note="or a second Drift RE, if the press drift needs to reach further")
    return remove_first("2Free-All-R1.pdf", LEV_FREEHUB) + [
        op("remove_2nd", "remove", "2nd", "2Free-All-R2.pdf", PRESS_OUT, one(p("pilot_short", "id")),
           [opt([p("drift_re", ">seat")], "default", "default")] +
           [opt(o["pieces"], "if clearance runs out near the end: " + o["when"], "manual") for o in LEV_FREEHUB],
           [ORING, extender], HW_TUBE, notes=[CIRCLIP_NOTE]),
        op("remove_both", "remove", "both", "2Free-All-RB.pdf", PRESS_OUT,
           one(p("pilot_short", "id"), p("pilot_long", "id", note="centres the far bearing and the spacer")),
           LEV_FREEHUB, [ORING, extender], HW_TUBE,
           notes=["Pushes both bearings and the spacer out in one pass.", CIRCLIP_NOTE]),
        op("install_1st", "install", "1st", "2Free-All-I1.pdf", PRESS_IN, one(p("pilot_short", "id")),
           one(p("stop_ctr", note="on the inboard end")),
           [ORING, p("spacer_tube", note="reaches down the freehub to the drift")], HW_TUBE),
        op("install_2nd", "install", "2nd", "2Free-All-I2.pdf", PRESS_IN,
           one(p("pilot_short", "id"), p("pilot_long", "id", note="sits in the 1st bearing and aligns the spacer")),
           one(p("drift_re", ">seat", note="on the inboard end of the freehub")), [p("o_ring", qty=3)],
           notes=[CIRCLIP_NOTE]),
    ]


ARRANGEMENTS = [
    dict(id="simple_pivot", name="Simple Pivot", image="Simple_Pivot.jpg", status="diagram",
         description="One bearing in a pivot.", operations=single_pivot_ops()),
    dict(id="double_stacked_pivot", name="Double Stacked Pivot", image="Double_Stacked_Pivot.jpg",
         status="confirmed", description="Two bearings side by side in one seat, installed from the same side. "
         "Same as a Simple Pivot, except the 1st bearing always comes out with the ALT Extractor.",
         operations=double_stacked_ops()),
    dict(id="bsb_pivot", name="BSB Pivot", image="BSB_Pivot.jpg", status="confirmed",
         description="Two bearings, one from each side, with a thin spacer ring between them. "
         "The ring is too thin for the ALT Drift, so the 1st bearing always comes out with the ALT Extractor.",
         operations=bsb_suspension_ops(thin_spacer=True)),
    dict(id="bsb_frame", name="BSB Frame", image="BSB_Frame.jpg", status="diagram",
         description="Two bearings, one from each side of a seat tube or linkage, with a tube spacer between them.",
         operations=bsb_suspension_ops()),
    dict(id="bsb_hub", name="BSB Hub", image="BSB_Hub.jpg", status="diagram",
         description="Open-bore hub: two bearings, one from each side, with a tube spacer between them.",
         operations=bsb_hub_ops()),
    dict(id="bsb_hub_no_spacer", name="BSB Hub Variant (No Spacer)", image="BSB_Hub_Variant_No_Spacer.jpg",
         status="confirmed", description="Open-bore hub with one bearing each side and nothing between them, "
         "so no Pilot Long is needed.", operations=bsb_hub_ops(no_spacer=True)),
    dict(id="over_axle", name="Over Axle (hub or frame main pivot)", image="Over_Axle_Hub.jpg", status="diagram",
         description="The bearings sit over a shouldered axle that stays between them and sticks out of them. "
         "Found in hubs and in some frame main pivots; the procedure is the same.",
         operations=over_axle_ops()),
    dict(id="over_axle_short", name="Over Axle Short", image="Over_Axle_Hub_Short.jpg", status="confirmed",
         description="Over-axle design whose axle enters the bearings but does not stick out of them, "
         "so no Over Axle Drift is needed.", operations=over_axle_short_ops()),
    dict(id="bsb_freehub", name="BSB Freehub", image="BSB_Freehub.jpg", status="diagram",
         description="Freehub with one bearing installed from each end and a spacer between them.",
         operations=freehub_each_side_ops()),
    dict(id="bsb_freehub_one_side", name="BSB Freehub Variant (One Side)", image="BSB_Freehub_Variant_One_Side.jpg",
         status="diagram",
         description="Freehub with both bearings installed from the outboard end: bearing, circlip, spacer, bearing.",
         operations=freehub_one_side_ops()),
]


# ---------------------------------------------------------------------------------------------------
# Assembly order
#
# For every job, what sits on the Stud from the pressing end to the leverage end, as drawn in the diagrams.
# The written instructions and the instruction drawings are both generated from this order.
#   "press:<piece>" / "center:<piece>" / "extra:<piece>"   one piece of that role
#   "leverage"            the leverage pieces of whichever option applies, from the part outwards
#   "nut"                 a fastener; "nut:plain" must be a plain nut, "nut:hold" is the one that must not turn
#                         "nut:pull" is the nut on the ALT Extractor's own stud
#   "bearing"             the bearing being installed        "bearing_in_part"   the bearing being removed
#   "other_bearing"       the bearing in the other seat      "spacer" / "axle" / "part" / "bore"   the workpiece
# ---------------------------------------------------------------------------------------------------
PUSH_OUT = ["nut", "press:drift_re", "center:pilot_short", "bearing_in_part", "leverage", "nut"]
PUSH_OUT_TUBE = ["nut:plain", "extra:spacer_tube"] + PUSH_OUT[1:]
PUSH_IN = ["nut", "press:drift_re", "center:pilot_short", "bearing", "part", "leverage", "nut"]
PUSH_IN_SECOND = ["nut", "press:drift_re", "center:pilot_short", "bearing", "spacer", "center:pilot_long",
                  "other_bearing", "leverage", "nut"]
OVER_AXLE_IN = ["nut", "press:drift_re", "press:oa_drift", "bearing"]

DO_PUSH_OUT = ("Tighten a nut. The drift pushes on the inner ring and the bearing comes out of its seat into the "
               "leverage piece. If the tool starts to sit crooked, stop and check.")
DO_PUSH_IN = ("Start the bearing square in its seat, then tighten a nut until the bearing is fully home. It takes "
              "little force: if it gets hard, stop and check that the bearing is straight.")
DO_ALT_DRIFT = ("Move the spacer off its axis so the ALT Drift can catch the back of the bearing's inner ring. Hold "
                "the fastener at the other end still and turn only the ALT Rod, with an Allen key in its end: the "
                "bearing is pushed out into the leverage piece.")
# confirmed by the tool's owner
DO_EXTRACTOR = ("First set the depth of the ALT Extractor for the width of the bearing. Place the extractor in the "
                "bearing and tighten the bolt in its head with an Allen key to expand the collet until it grips. "
                "Slide the Sleeve and then the Step onto the extractor's stud, fit the Stud Stop behind them as the "
                "nut, and extract: the bearing is pulled out into the sleeve.")
DO_AXLE_OUT = ("Tighten a nut. The pressing piece pushes on the end of the axle, and the axle carries the bearing on "
               "its other end out of the seat into the leverage piece.")
DO_OVER_AXLE = ("Tighten a nut. The Over Axle Drift slides over the axle and pushes the bearing into its seat. "
                "Always push the Over Axle Drift with the Drift RE, never with the nut.")
DO_BOTH_OUT = ("Tighten a nut. The drift pushes the first bearing, which pushes the spacer and the second bearing "
               "ahead of it, and all three come out into the leverage piece.")
DO_BOTH_IN = "Tighten a nut. The two bearings are pushed into their seats against each other until both are home."


def assembly(arr_id, o):
    """(stack, action) of one operation."""
    i = o["id"]
    over_axle, short = arr_id == "over_axle", arr_id == "over_axle_short"
    hub = arr_id in ("bsb_hub", "bsb_hub_no_spacer") or over_axle or short

    if i.startswith("remove_1st_extractor"):
        # the extractor goes into the bearing from the sleeve side; its own stud points out through the sleeve
        return ["bearing_in_part", "press:alt_extractor", "leverage", "nut:pull"], DO_EXTRACTOR
    if i.startswith("remove_1st"):
        if short:
            return ["nut", "press:pilot_short", "axle", "bearing_in_part", "leverage", "nut"], DO_AXLE_OUT
        if over_axle:
            near, far = ("pilot_short", "pilot_long") if i.endswith("disc") else ("pilot_long", "pilot_short")
            return ["nut", "press:drift_re", f"center:{near}", "axle", f"center:{far}", "bearing_in_part",
                    "leverage", "nut"], DO_AXLE_OUT
        # the rod reaches the first bearing from the far side, through the other bearing and the spacer
        return ["press:alt_rod", "other_bearing", "spacer", "press:alt_drift", "center:pilot_short",
                "bearing_in_part", "leverage", "nut:hold"], DO_ALT_DRIFT
    if i == "remove_both":
        return ["nut:plain", "extra:spacer_tube", "press:drift_re", "center:pilot_short", "bearing_in_part",
                "spacer", "center:pilot_long", "other_bearing", "leverage", "nut"], DO_BOTH_OUT
    if i.startswith("remove_2nd"):
        return PUSH_OUT_TUBE, DO_PUSH_OUT
    if i in ("remove", "2nd_remove"):
        return PUSH_OUT, DO_PUSH_OUT

    if i == "install_both":
        if over_axle:
            return OVER_AXLE_IN + ["center:pilot_long", "axle", "center:pilot_short", "other_bearing",
                                   "press:oa_drift", "press:drift_re", "nut"], DO_BOTH_IN
        if arr_id == "bsb_hub_no_spacer":
            return ["nut", "press:drift_re", "center:pilot_short", "bearing", "part", "other_bearing",
                    "center:pilot_short", "press:drift_re", "nut"], DO_BOTH_IN
        return ["nut", "press:drift_re", "center:pilot_short", "bearing", "spacer", "center:pilot_long",
                "center:pilot_short", "other_bearing", "press:oa_drift", "press:drift_re", "nut"], DO_BOTH_IN
    if i == "install_1st_drive_bore":
        return OVER_AXLE_IN + ["center:pilot_short", "axle", "center:pilot_long", "bore", "leverage", "nut"], DO_OVER_AXLE
    if i == "install_2nd_disc_bearing":
        return OVER_AXLE_IN + ["center:pilot_long", "axle", "center:pilot_short", "other_bearing", "leverage",
                               "nut"], DO_OVER_AXLE
    if over_axle and i.startswith("install_2nd"):
        near, far = ("pilot_long", "pilot_short") if i.endswith("disc") else ("pilot_short", "pilot_long")
        return OVER_AXLE_IN + [f"center:{near}", "axle", f"center:{far}", "other_bearing", "leverage", "nut"], DO_OVER_AXLE
    if short and i == "install_2nd":
        return ["nut", "press:drift_re", "center:pilot_short", "bearing", "center:pilot_short", "axle",
                "other_bearing", "leverage", "nut"], DO_PUSH_IN
    if i.startswith("install_2nd"):
        return PUSH_IN_SECOND, DO_PUSH_IN
    if i.startswith("install_1st") and hub:
        return ["nut", "press:drift_re", "center:pilot_long", "bearing", "part", "leverage", "nut"], DO_PUSH_IN
    if i == "install_1st" and arr_id == "bsb_freehub_one_side":
        return ["nut:plain", "extra:spacer_tube"] + PUSH_IN[1:], DO_PUSH_IN
    if i in ("install", "1st_install", "2nd_install", "install_1st"):
        return PUSH_IN, DO_PUSH_IN
    raise ValueError(f"no assembly order for {arr_id}/{i}")


# ---------------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------------
def fmt_piece(d):
    s = PIECES[d["piece"]]
    if d.get("qty", 1) > 1:
        s = f"{d['qty']} x {s}"
    if d.get("size"):
        s += f" [{SIZES[d['size']]}]"
    if d.get("note"):
        s += f" ({d['note']})"
    return s


def fmt_role(options):
    out = []
    for o in options:
        body = " + ".join(fmt_piece(x) for x in o["pieces"]) or "none"
        out.append(f"{body} — *{o['when']}*" if o["when"] else body)
    return "<br>**or** ".join(out) if out else "none"


def op_title(o):
    if o["title"]:
        return o["title"]
    which = {"single": "", "1st": " 1st bearing", "2nd": " 2nd bearing", "both": " both bearings"}[o["bearing"]]
    side = f", {o['side']} side" if o["side"] else ""
    variant = f" with the {o['variant']}" if o["variant"] else ""
    return f"{o['operation'].capitalize()}{which}{side}{variant}"


def bill_of_materials(arr):
    """Every piece that any operation of the arrangement can call for: (piece, size) -> (max qty, only sometimes?)."""
    bom = {}
    for o in arr["operations"]:
        groups = [o["press"], o["center"], o["leverage"], [opt(o["extras"])], [opt(o["hardware"]["pieces"])]]
        for options in groups:
            for option in options:
                conditional = len(options) > 1 or bool(o["when"])
                for d in option["pieces"]:
                    key = (d["piece"], d.get("size"))
                    qty, cond = bom.get(key, (0, True))
                    bom[key] = (max(qty, d.get("qty", 1)), cond and conditional)
    return bom


def render_md(arrangements):
    L = ["# ALT/ALT press rules", "",
         "Generated by `build_rules.py` — edit that file, not this one.", "",
         "Each row is one job on one bearing. A complete tool is: press + centre + leverage + extras + hardware.",
         "Where a cell offers alternatives, pick the one whose condition applies.", "",
         "Status: **diagram** = transcribed from an altalt.ca instructional diagram; "
         "**confirmed** = not drawn on the site, confirmed by the tool's owner; "
         "**inferred** = assumed, still needs confirmation.", "",
         "## General rules", ""]
    L += [f"- {n}" for n in GENERAL_NOTES]
    L += ["", "## Open questions", ""] + [f"{i}. {q}" for i, q in enumerate(OPEN_QUESTIONS, 1)]
    for a in arrangements:
        L += ["", f"## {a['name']}", "", f"{a['description']} Status: **{a['status']}**. "
              f"Picture: `data/altalt_site/arrangements/{a['image']}`", "",
              "| Job | Press | Centre | Leverage | Extras | Hardware | Source |",
              "|---|---|---|---|---|---|---|"]
        for o in a["operations"]:
            src = f"{o['status']}" + (f": `{o['diagram']}`" if o["diagram"] else "")
            job = op_title(o) + (f"<br>*when: {o['when']}*" if o["when"] else "")
            extras = " + ".join(fmt_piece(x) for x in o["extras"]) or "none"
            hw = " + ".join(fmt_piece(x) for x in o["hardware"]["pieces"])
            L.append(f"| {job} | {fmt_role(o['press'])} | {fmt_role(o['center'])} | "
                     f"{fmt_role(o['leverage'])} | {extras} | {hw} | {src} |")
        notes = []
        for o in a["operations"]:
            for n in o["notes"] + [o["hardware"]["note"]]:
                if n not in notes:
                    notes.append(n)
        L += [""] + [f"- {n}" for n in notes]
        L += ["", "**All pieces this arrangement can need** (removal and install of every bearing; "
                  "`*` = only in some cases):", ""]
        for (piece, size), (qty, cond) in bill_of_materials(a).items():
            sz = f" [{SIZES[size]}]" if size else ""
            L.append(f"- {qty} x {PIECES[piece]}{sz}{' *' if cond else ''}")
    return "\n".join(L) + "\n"


def main():
    for a in ARRANGEMENTS:
        for o in a["operations"]:
            o["title"] = op_title(o)
            o["stack"], o["action"] = assembly(a["id"], o)
    data = {
        "source": "https://www.altalt.ca/instructional-diagrams",
        "pieces": PIECES,
        "size_rules": SIZES,
        "available_sizes": AVAILABLE_SIZES,
        "general_notes": GENERAL_NOTES,
        "open_questions": OPEN_QUESTIONS,
        "arrangements": ARRANGEMENTS,
    }
    (HERE / "rules.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    (HERE / "RULES.md").write_text(render_md(ARRANGEMENTS))
    n_ops = sum(len(a["operations"]) for a in ARRANGEMENTS)
    print(f"{len(ARRANGEMENTS)} arrangements, {n_ops} operations")


if __name__ == "__main__":
    main()
