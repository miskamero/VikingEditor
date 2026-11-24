VALHEIM_BEARDS = {
    "Beard23": "Crumb Catcher",
    "Beard11": "Facewarmer",
    "Beard26": "Handlebar",
    "Beard6": "Loose Braid",
    "Beard1": "Majestic",
    "Beard15": "Mini Braid",
    "Beard22": "Mustache",
    "Beard12": "Royal",
    "Beard3": "Short",
    "Beard5": "Single Braid",
    "Beard14": "Split Braid",
    "Beard7": "Split Shave",
    "Beard16": "Stonedweller",
    "Beard4": "Straight",
    "Beard8": "Thick",
    "Beard21": "Tidy",
    "Beard10": "Top Braid",
    "Beard25": "Trimmed",
    "Beard13": "Triplets",
    "Beard9": "Trobadour",
    "Beard2": "Twin Braids",
    "Beard24": "Waxed",
    "Beard20": "Spiky",
    "Beard18": "Jarl Braids",
    "Beard17": "Neat",
    "Beard19": "Bushy",
}

sorted_beards = dict(
    sorted(VALHEIM_BEARDS.items(), key=lambda item: item[1].lower())
)

VALHEIM_BEARDS = {"BeardNone": "No Beard", **sorted_beards}
