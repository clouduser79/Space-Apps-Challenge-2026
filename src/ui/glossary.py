"""Kid-friendly glossary for the space and science words used in the game.

`GLOSSARY` maps each term (as shown in the pop-up title) to a 1-2 sentence
explanation written for roughly a 5th-grade reader, usually with an
everyday comparison. `ALIASES` maps other spellings, plurals that aren't
just "+s", and abbreviations to their main entry.

`find_terms(text)` locates glossary words inside any piece of UI text so
`GlossaryText` (src/ui/widgets.py) can turn them into clickable links.
To add a word, add one line to GLOSSARY (and optionally ALIASES) —
nothing else needs to change.
"""

from __future__ import annotations

import re
from functools import lru_cache

GLOSSARY: dict[str, str] = {
    # --- Orbits & getting around space ---------------------------------
    "Orbit": "The path a spacecraft or moon takes as it travels around a "
             "planet or star. Gravity keeps pulling it inward, like a ball on "
             "a string you swing in a circle.",
    "Low Earth Orbit": "An orbit only a few hundred kilometres above Earth. The "
                       "International Space Station flies here and circles the "
                       "whole planet in about 90 minutes!",
    "Sun-Synchronous Orbit": "An orbit over the North and South Poles that passes "
                             "over each place at the same time of day — so photos "
                             "always have the same lighting, like taking a picture "
                             "of your house every day at noon.",
    "Geostationary Orbit": "A very high orbit where a satellite goes around exactly "
                           "as fast as Earth spins, so it seems to hover over one "
                           "spot. TV satellites live here.",
    "Lagrange point": "A balance spot in space where the pulls of the Sun and Earth "
                      "even out, so a spacecraft can 'park' there — like a marble "
                      "resting in a tiny dip between two hills.",
    "Lunar": "Anything to do with the Moon. A lunar orbit goes around the Moon.",
    "Altitude": "How high something is above the ground. Planes fly at about "
                "10 km; the Space Station is about 400 km up.",
    "Inclination": "How tilted an orbit is compared to the equator. 0° circles the "
                   "middle like a belt; 90° goes over the poles like a ribbon "
                   "wrapped around a gift.",
    "Polar orbit": "An orbit that passes over the North and South Poles. As Earth "
                   "spins underneath, the spacecraft eventually sees every part of "
                   "the planet.",
    "Orbital period": "How long it takes to go around once. The Moon's period is "
                      "about a month; the Space Station's is 90 minutes.",
    "Longitude": "Imaginary lines running from the North Pole to the South Pole "
                 "that tell you how far east or west a place is on Earth.",
    "Atmospheric drag": "Air pushing against a moving object and slowing it down — "
                        "like the wind on your hand out of a car window. Even the "
                        "thin air high up slowly pulls satellites back down.",
    "Eclipse": "When a planet blocks the Sun's light. The spacecraft goes into "
               "shadow, and its solar panels stop making power until it comes "
               "out again.",
    "Station-keeping": "Small engine pushes that keep a spacecraft in the right "
                       "spot, like gently steering your bike to keep riding in a "
                       "straight line.",
    "Cruise phase": "The long trip from Earth to your target. It's like the hours "
                    "on the highway during a road trip — not much happens, but "
                    "you have to wait it out.",
    "Transfer": "Firing the engine to move from one orbit to another — like "
                "changing lanes on a highway to take an exit.",
    "Geostationary transfer orbit": "A stretched-out orbit a rocket uses as a "
                                    "stepping stone on the way up to geostationary "
                                    "orbit (GTO for short).",
    "Escape velocity": "The speed you need to break free of Earth's gravity and "
                       "not fall back: about 11 kilometres every second!",
    "Interplanetary": "Travelling between planets — leaving Earth behind to visit "
                      "another world.",
    "Deep space": "Space far away from Earth, beyond the Moon.",
    "Trajectory": "The path a spacecraft follows through space, like the arc a "
                  "basketball makes on its way to the hoop.",
    "Coverage": "How much of a planet your spacecraft can see. Good coverage "
                "means it can look at almost every place.",
    "Revisit": "How often a spacecraft passes over the same place again — like "
               "how often a school bus comes back to your stop.",
    "Radiation": "Invisible energy from the Sun and space that can damage "
                 "electronics — a bit like how too much sun gives you sunburn.",
    "Light-time": "How long light (and radio messages) take to travel. Signals to "
                  "far-away planets can take hours to arrive!",

    # --- Spacecraft parts ----------------------------------------------
    "Spacecraft bus": "The main body of a spacecraft that holds everything "
                      "together and keeps it alive — like the frame, battery and "
                      "wires of a car.",
    "Payload": "The useful stuff a spacecraft carries to do its job. For science "
               "missions, that's the instruments.",
    "Avionics": "The spacecraft's brain: the computers that control it and store "
                "its data.",
    "Attitude control": "The system that turns and points the spacecraft (nothing "
                        "to do with its mood!). It's like turning your head to "
                        "look at something.",
    "Nadir": "Straight down, toward the planet below. Nadir pointing means the "
             "spacecraft always looks at the ground.",
    "Arcsecond": "A super-tiny angle — 3,600 of them fit in one degree. Pointing "
                 "that precisely is like aiming at a coin from 4 km away.",
    "Solar array": "A set of solar panels that turn sunlight into electricity.",
    "Radioisotope generator": "A power source (RTG) that makes electricity from "
                              "the heat of slowly decaying radioactive material. It "
                              "works even in the dark, far from the Sun.",
    "Propulsion": "The engines and fuel that push a spacecraft to speed up, slow "
                  "down or turn.",
    "Manoeuvre": "A planned move, like firing the engines to change direction or "
                 "orbit.",
    "X-band": "A type of radio wave used to talk to spacecraft. It's reliable but "
              "carries data slower than Ka-band.",
    "Ka-band": "A type of radio wave that can carry lots of data quickly — like a "
               "wider pipe that lets more water through.",
    "Downlink": "Sending data from the spacecraft down to Earth. A faster "
                "downlink gets your photos home sooner.",
    "Ground station": "A giant radio dish on Earth that talks to spacecraft.",
    "Data backlog": "Data waiting in line because it can't be sent home fast "
                    "enough — like a growing pile of homework.",
    "Safe mode": "When something goes wrong, the spacecraft turns off extra "
                 "systems and waits for help from Earth — like pausing a game.",
    "Structure": "The skeleton of the spacecraft that everything bolts onto.",

    # --- Instruments & science ------------------------------------------
    "Imager": "A camera built for space. Imaging just means taking pictures.",
    "Spectrometer": "An instrument that splits light into a rainbow to find out "
                    "what things are made of — every material leaves its own "
                    "colour 'fingerprint'.",
    "Spectroscopy": "Studying the rainbow of light from something to learn what "
                    "it's made of.",
    "Composition": "What something is made of, like the ingredients in a recipe.",
    "Radar sounder": "An instrument that sends radio waves into the ground and "
                     "listens for the echoes — like a bat — to see what's hidden "
                     "underneath.",
    "Subsurface": "Under the surface — below the ground or ice.",
    "Geology": "The study of rocks and how a planet's surface was formed.",
    "Plume": "A jet of gas or water shooting out from a surface, like a geyser.",
    "Magnetometer": "A super-sensitive compass that measures magnetic fields in "
                    "space.",
    "Magnetic field": "An invisible force around magnets — and around planets like "
                      "Earth — that makes compasses point north.",
    "Space weather": "Changing conditions in space caused by the Sun, like storms "
                     "of tiny charged particles that can harm satellites.",
    "Solar wind": "A constant stream of tiny particles blowing out from the Sun "
                  "in every direction.",
    "Solar flare": "A sudden, enormous burst of energy from the Sun's surface.",
    "Sample return": "Collecting rocks or dust on another world and flying them "
                     "back to Earth for scientists to study.",
    "Reconnaissance": "Exploring an area to gather information — scouting it out.",
    "Micrometeorite": "A speck of space rock, smaller than a grain of sand, "
                      "travelling faster than a bullet.",
    "Context imaging": "Wide pictures that show the big picture around a "
                       "target, so scientists know where the close-up photos fit.",

    # --- Rockets & mission planning --------------------------------------
    "Launch vehicle": "The rocket that carries your spacecraft from the ground "
                      "into space.",
    "CubeSat": "A tiny satellite about the size of a loaf of bread.",
    "Flagship": "The biggest, most important — and most expensive — kind of "
                "mission or rocket.",
    "Reliability": "How likely something is to work. 97% reliable means it works "
                   "97 times out of 100.",
    "Margin": "Extra room you keep just in case — like leaving home early in case "
              "there's traffic.",
    "Trade-off": "Giving up some of one thing to get more of another, like "
                 "spending allowance on a game instead of snacks.",
    "Anomaly": "Something unexpected going wrong during the mission.",
    "Feasible": "Possible to actually do.",
    "Objective": "The goal your mission is trying to reach.",
    "Astronomical unit": "The distance from Earth to the Sun — about 150 million "
                         "km. Scientists use it (AU) to measure distances in the "
                         "solar system.",
    "Ice giant": "A huge planet made mostly of icy water, ammonia and methane, "
                 "like Uranus and Neptune.",
    "Methane": "A gas made of carbon and hydrogen. It makes Uranus and Neptune "
               "look blue.",
    "GMAT": "NASA's free mission-planning software. This game uses it to "
            "calculate real orbit numbers when it's available.",
}

# Other ways a term is written -> the GLOSSARY entry it should open
ALIASES: dict[str, str] = {
    "Orbits": "Orbit", "Orbiting": "Orbit", "Orbited": "Orbit",
    "LEO": "Low Earth Orbit", "Low Earth orbits": "Low Earth Orbit",
    "SSO": "Sun-Synchronous Orbit",
    "GEO": "Geostationary Orbit", "Geostationary": "Geostationary Orbit",
    "L1": "Lagrange point", "Sun-Earth L1": "Lagrange point",
    "Lagrange points": "Lagrange point",
    "Inclined": "Inclination",
    "Period": "Orbital period",
    "Drag": "Atmospheric drag",
    "GTO": "Geostationary transfer orbit", "Escape": "Escape velocity",
    "Eclipses": "Eclipse",
    "Cruise": "Cruise phase",
    "Transfer burn": "Transfer",
    "Bus": "Spacecraft bus",
    "Onboard computer": "Avionics",
    "ADCS": "Attitude control", "Attitude": "Attitude control",
    "Solar arrays": "Solar array",
    "RTG": "Radioisotope generator", "RTGs": "Radioisotope generator",
    "Maneuver": "Manoeuvre", "Manoeuvres": "Manoeuvre", "Maneuvers": "Manoeuvre",
    "Ground stations": "Ground station",
    "Backlog": "Data backlog",
    "Imaging": "Imager", "Imagers": "Imager",
    "Radar": "Radar sounder",
    "Plumes": "Plume",
    "Magnetic fields": "Magnetic field",
    "Solar flares": "Solar flare", "Flare": "Solar flare", "Flares": "Solar flare",
    "Micrometeorites": "Micrometeorite",
    "Launcher": "Launch vehicle", "Launchers": "Launch vehicle",
    "AU": "Astronomical unit",
    "Ice giants": "Ice giant",
    "Anomalies": "Anomaly",
    "Trade-offs": "Trade-off",
    "Objectives": "Objective",
    "Margins": "Margin",
}

# Abbreviations must match exactly ("AU" yes, "au" inside words no);
# everything else matches case-insensitively.
_CASE_SENSITIVE = {"LEO", "SSO", "GEO", "GTO", "L1", "ADCS", "RTG", "RTGs", "AU", "GMAT",
                   "CubeSat", "X-band", "Ka-band"}


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern:
    """One regex for every term and alias, longest first so 'Low Earth
    Orbit' wins over 'Orbit'. Case-sensitive words use an inline flag."""
    words = sorted(set(GLOSSARY) | set(ALIASES), key=len, reverse=True)
    parts = []
    for word in words:
        body = re.escape(word)
        parts.append(body if word in _CASE_SENSITIVE else f"(?i:{body})")
    # Whole words only. A trailing hyphen is fine ("CubeSat-scale"), a
    # leading one is not ("non-orbit" shouldn't link "orbit").
    return re.compile(r"(?<![\w-])(?:" + "|".join(parts) + r")(?!\w)")


_LOOKUP = {k.lower(): k for k in GLOSSARY} | {k.lower(): v for k, v in ALIASES.items()}


def canonical(word: str) -> str | None:
    """The GLOSSARY entry a matched word refers to."""
    return _LOOKUP.get(word.lower())


def find_terms(text: str) -> list[tuple[int, int, str]]:
    """(start, end, entry) for glossary words in `text`.

    Only the first mention of each entry is linked, so a sentence never
    turns into a wall of underlines.
    """
    found, seen = [], set()
    for match in _pattern().finditer(text):
        entry = canonical(match.group(0))
        if entry and entry not in seen:
            seen.add(entry)
            found.append((match.start(), match.end(), entry))
    return found


def define(entry: str) -> str:
    return GLOSSARY[entry]
