SYSTEM = (
    "You help a mechanic who sells a bearing press for mountain bikes. From a bike's exploded diagram he needs to "
    "know exactly which cartridge bearings it uses, so that the right press pieces can be chosen. A wrong bearing code means the wrong tool is shipped, so never guess a code or a size: when something "
    "is not stated, say it is not found."
)

EXTRACT = """\
This is the exploded diagram (or parts list) of a bike frame or component. Look at both the text and the drawings.

1. List every distinct cartridge bearing whose code is printed, e.g. "6902 2RS", "61804 2RSR", "MR 15267". \
Write the code as a bearing code: keep seal and ring markings (2RS, 2Z, LLU, MAX, E, FO, ...), leave out brand \
names, quantities and the manufacturer's own part numbers. If the diagram gives a bearing's size instead of a \
code (for example "Bearing 17x30x7"), that identifies it too: list it with the size as its code, written \
"17x30x7" (inner diameter x outer diameter x width). Headset and bottom bracket bearings are not needed.

2. If a bearing is shown with neither a code nor a size (only a part number, a kit name or a position number), \
list it as an unresolved reference with whatever identifies it, so it can be looked up.

Also give the manufacturer and model if the document names them.
"""

RESOLVE = """\
An exploded diagram of a {bike} shows the bearings below without giving their bearing codes. Find the standard \
bearing code of each one (for example "6902 2RS").

{references}

Search the manufacturer's own website and documents first (parts lists, bearing kits, service manuals), then \
shops that sell the manufacturer's bearing kits. Open the pages to read the actual code. For each reference, \
report the bearing code, the page where you read it, and anything uncertain. If you cannot find a page that \
states the code, say it was not found: do not infer a code from similar models.
"""

DIMENSIONS = """\
Find the dimensions in millimetres of these bearings: inner diameter, outer diameter and width. For bearings with \
an extended inner ring also give the width over the inner ring; for flanged bearings also give the flange diameter.

{codes}

Use a bearing manufacturer's own catalogue or product page as the source (Enduro Bearings, SKF, NTN, NSK, FAG, \
...), and open the page to read the numbers. For each bearing report the dimensions and the page where you read \
them. If you cannot find a page that states them, say they were not found.
"""

STRUCTURE = """\
Below are the findings of a web search. Put them into the requested format. Copy codes, numbers and URLs exactly \
as stated; where the findings say something was not found or do not mention it, use null.

Items that were asked about: {items}

Findings:
{findings}
"""
