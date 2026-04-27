#!/usr/bin/env python3
"""AI-driven opening scene for the first playable moment."""

OPENING_SCENE_TITLE = "Your Awakening in Elyndor"

CHARACTER_CREATION_DIALOG = """

You awaken with a violent jolt — not from sleep, but from being torn through reality itself.

One moment you are going about your normal routine, the next you are waking in an endless void. You are between worlds. Between realities.

A new life lies before you, but first you must remember who you were...

"""
OPENING_SCENE_TEXT = """
YOUR AWAKENING IN ELYNDOR

You awaken with a violent jolt — not from sleep, but from being torn through reality itself.

One moment you were in your world. The next, you're slammed into damp earth and leaf litter, gasping for breath. Your heart hammers. The air smells of smoke, blood, and something acrid — like ozone mixed with sulfur.

You're on a gentle forested slope. Through the bushes and trees you have cover, but only barely.

A hundred yards down the road, a caravan is being massacred.

Three wagons are stopped on the dirt road. Screams echo as demonic monstrosities — hunched, grey-skinned, creatures the size of large men with jagged-toothed and 4 arms each rip into the travelers with claws and crude weapons. Their laughter is guttural and wet. Bodies are being torn apart with horrifying casualness.

Above it all, circling lazily in the sky, is a winged demon — taller, more elegant, with leathery wings and burning red eyes. It watches the slaughter like a conductor overseeing an orchestra.

You are hidden... for now.

A slight movement just an arm's length away draws your attention. Half-hidden by the same bushes that hide you lies a bleeding woman with feline ears and a tail. She's unconscious, bleeding from a gash all over her body. Her wrists are bound with heavy iron chains. A bright red tattoo glows faintly on the side of her neck.

As you watch, she collapses into the dirt, not yet hidden from the slaughter. You don't know if she saw you or not, but if any of the demons glance up the hill, they will almost certainly see her and if you're still there, they will find you too. 

""".strip()

OPENING_SCENE_FACTS = [
    "The player has just arrived in Elyndor and is hidden on a forested slope above a caravan ambush.",
    "A caravan is being massacred one hundred yards away by a group of four-armed grey-skinned demons.",
    "A winged demon circles above the massacre enjoying the carnage below.",
    "A wounded unconscious nekko woman with feline ears and a tail lies nearby, chained and marked by a faintly glowing red tattoo on her neck.",
    "The tattoo on the girl is a slave mark, used by all races and made to be difficult to hide or remove. It glows a faint but steady red.",
    "The player and the wounded woman are not yet noticed, but remaining exposed risks discovery by the demons.",
    "The caravan travelers and attacking demons are currently unnamed scene groups, not individually tracked NPCs.",
]


def get_opening_scene_text() -> str:
    """Return the opening scenario that starts a new game."""
    return OPENING_SCENE_TEXT

def get_character_creation_text() -> str:
    """Return the opening scenario that starts a new game."""
    return CHARACTER_CREATION_DIALOG

def get_opening_scene_facts() -> list[str]:
    """Return durable opening-scene facts for the game state."""
    return list(OPENING_SCENE_FACTS)


def show_opening_scene():
    """Display the dramatic opening scene - AI will handle player response."""
    print(f"""
╔════════════════════════════════════════════════════════════╗
║              🔥 YOUR AWAKENING IN ELYNDOR 🔥                ║
╚════════════════════════════════════════════════════════════╝

{OPENING_SCENE_TEXT}
""")
