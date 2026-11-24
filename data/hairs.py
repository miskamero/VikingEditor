VALHEIM_HAIRS = {
    "Hair1": "Windswept",
    "Hair2": "High Ponytail",
    "Hair3": "Pigtails",
    "Hair4": "Low Ponytail",
    "Hair5": "Short",
    "Hair6": "Long and Loose",
    "Hair7": "Dragonslayer",
    "Hair8": "Parted",
    "Hair9": "Old One-Eye",
    "Hair10": "Side Swept",
    "Hair11": "Long Braid",
    "Hair12": "Matronly",
    "Hair13": "Twin Braids",
    "Hair14": "Speed Demon",
    "Hair15": "Pulled Back Curls",
    "Hair16": "Gathered Braids",
    "Hair17": "Neat Braids",
    "Hair18": "Royal Braids",
    "Hair19": "Painter Curls",
    "Hair20": "Tidy Curls",
    "Hair21": "Twin Buns",
    "Hair22": "Single Bun",
    "Hair23": "Short Curls",
    "Hair24": "Shaved and Braided",
    "Hair25": "Knot",
    "Hair26": "Short Locs",
    "Hair27": "Braids of Strength",
    "Hair28": "Merchant's Braid",
    "Hair29": "Tucked Back",
    "Hair30": "Loose Waves",
    "Hair31": "Gathered Locs",
    "Hair32": "Mullet",
    "Hair33": "Vinland Shave",
    "Hair34": "Castellan",
    "Hair35": "Champion",
    "Hair36": "Chronicler",
    "Hair37": "Sunbringer",
    "Hair38": "Masculine",
}

# sort alphabetically
sorted_hairs = dict(
    sorted(VALHEIM_HAIRS.items(), key=lambda item: item[1].lower())
)

VALHEIM_HAIRS = {"HairNone": "No Hair", **sorted_hairs}
