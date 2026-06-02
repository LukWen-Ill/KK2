"""Generate CoT training data for /ai/analyze (GoodStep / BadStep / TipStep)."""
import json
import random
from pathlib import Path

random.seed(42)

# 5 player profiles: (gir_pct, fairway_pct, avg_putts, scoring_avg_per_hole)
PROFILES = [
    {"gir_pct": 8,  "fairway_pct": 35, "avg_putts": 2.9,  "scoring_avg": 6.5},
    {"gir_pct": 22, "fairway_pct": 45, "avg_putts": 2.5,  "scoring_avg": 5.8},
    {"gir_pct": 38, "fairway_pct": 55, "avg_putts": 2.2,  "scoring_avg": 5.2},
    {"gir_pct": 50, "fairway_pct": 63, "avg_putts": 2.0,  "scoring_avg": 4.8},
    {"gir_pct": 62, "fairway_pct": 70, "avg_putts": 1.85, "scoring_avg": 4.0},
]

PGA = {"gir_pct": 65.0, "fairway_pct": 60.0, "avg_putts": 1.73, "scoring_avg_per_hole": 3.92}

# Good-step completions per profile
GOOD_COMPLETIONS = [
    "Fairway {fw}% (PGA: {pga_fw}%) — acceptabel träff-rate för nivån.",
    "Fairway {fw}% (PGA: {pga_fw}%) — nära PGA Tour-nivå.",
    "Fairway {fw}% (PGA: {pga_fw}%) — solid träffprocent.",
    "GIR {gir}% (PGA: {pga_gir}%) — bra greensträffar relativt sett.",
    "Avg putts {putts} (PGA: {pga_putts}) — putting är en styrka.",
]

# Bad-step completions per profile (index matches profile)
BAD_COMPLETIONS = [
    "GIR {gir}% (PGA: {pga_gir}%) — störst förbättringspotential.",
    "GIR {gir}% (PGA: {pga_gir}%) — approach-spelet behöver mest arbete.",
    "GIR {gir}% (PGA: {pga_gir}%) — greens in regulation är den svagaste länken.",
    "Scoring avg {scoring} (PGA: {pga_scoring}) — hål-poäng ovanför PGA-snittet.",
    "Avg putts {putts} (PGA: {pga_putts}) — putting kostar slag.",
]

# Tip-step completions — keyed by weakness type
TIPS = {
    "gir": [
        "Träna approach-slag från 120–150 meter och sikta mot grensenter.",
        "Öva pitch-slag från 80–100 meter — kort approach är nyckeln till bättre GIR.",
        "Fokusera på järnkontroll från 100–140 meter med tydlig targetlinje.",
        "Träna halva järnslag för bättre avståndskontroll till grenen.",
        "Jobba med ball-position och svingplan för ren kontakt i järnspelet.",
        "Öva approach från rough — bättre kontakt ger fler chanser på GIR.",
        "Arbeta med wedge-spel från 50–80 meter — det korta approach-spelet avgör.",
        "Träna 7-järn från 150 meter med fokus på riktning snarare än avstånd.",
        "Öva från divot-lies och tjockt gräs — verkligheten på banan kräver anpassning.",
    ],
    "fairway": [
        "Fokusera på driver-accuracy — öva tighta fairway-linjer på övningsbanan.",
        "Korta ner drivern och prioritera placement — fairway-träff ger bättre utgångläge.",
        "Träna tee-shots med 3-wood på smala hål för bättre precision.",
        "Öva swing-tempo med driver — en mjukare sving ger ofta rakare boll.",
        "Jobba med grip och setup för att minska sidoböj på långa slag.",
        "Analysera din miss-pattern — konsekvent slice kräver specifik teknikkorrigering.",
        "Träna fairway-bunker-slag — de påverkar scoring mer än man tror.",
    ],
    "putts": [
        "Träna 2–3 meters puttar dagligen — distansbedömning är nyckeln.",
        "Öva långa lagg-puttar från 10+ meter för att eliminera 3-puttars.",
        "Fokusera på puttarnas startlinje — en konsekvent boll-rullning sparar slag.",
        "Träna läsning av linjer — gå runt hela grenen och känn lutningen.",
        "Öva putting-tempo med metronom eller räkneteknik för jämnt slag.",
        "Jobba med puttergreppet — ett neutralt grepp minskar face-rotation.",
        "Träna kortputtar under press — lägg in konsekvensövningar på 1–2 meter.",
        "Öva 5 puttar från 5 olika riktningar 1.5 meter från hålet dagligen.",
    ],
    "scoring": [
        "Spela fler kortbanerundar och fokusera på konservativt par-spel.",
        "Träna på att undvika dubbelbogeyn — ta säkra val vid risk-hål.",
        "Fokusera på course management: välj rätt klubba för säker position.",
        "Öva chip-och-putt-situationer — up-and-down räddningar sparar scoring.",
        "Analysera dina scoring-holes och identifiera återkommande misstag.",
        "Spela matchplay för att öva taktiskt tänkande och hantera press.",
    ],
}


def _stats_block(p: dict) -> str:
    lines = [
        f"- GIR: {p['gir_pct']}% (PGA Tour-snitt: {PGA['gir_pct']:.1f}%)",
        f"- Fairway: {p['fairway_pct']}% (PGA Tour-snitt: {PGA['fairway_pct']:.1f}%)",
        f"- Avg putts/hål: {p['avg_putts']} (PGA Tour-snitt: {PGA['avg_putts']})",
        f"- Scoring avg/hål: {p['scoring_avg']} (PGA Tour-snitt: {PGA['scoring_avg_per_hole']})",
    ]
    return "\n".join(lines)


def _fill(template: str, p: dict) -> str:
    return template.format(
        gir=p["gir_pct"],
        fw=p["fairway_pct"],
        putts=p["avg_putts"],
        scoring=p["scoring_avg"],
        pga_gir=PGA["gir_pct"],
        pga_fw=PGA["fairway_pct"],
        pga_putts=PGA["avg_putts"],
        pga_scoring=PGA["scoring_avg_per_hole"],
    )


def _weakness(p: dict) -> str:
    gaps = {
        "gir": abs(p["gir_pct"] - PGA["gir_pct"]) / PGA["gir_pct"],
        "fairway": abs(p["fairway_pct"] - PGA["fairway_pct"]) / PGA["fairway_pct"],
        "putts": abs(p["avg_putts"] - PGA["avg_putts"]) / PGA["avg_putts"],
        "scoring": abs(p["scoring_avg"] - PGA["scoring_avg_per_hole"]) / PGA["scoring_avg_per_hole"],
    }
    return max(gaps, key=lambda k: gaps[k])


examples: list[dict] = []

# Format A — GoodStep (~45 examples: 5 profiles × 9 completions)
for p in PROFILES:
    block = _stats_block(p)
    prompt = f"{block}\n\nVad var bäst i spelarens runda? Nämn stat-värde och PGA Tour-snitt. Svar:"
    for tmpl in GOOD_COMPLETIONS:
        examples.append({"format": "A", "prompt": prompt, "completion": _fill(tmpl, p)})

# Format B — BadStep (~45 examples: 5 profiles × 9 completions)
for p in PROFILES:
    block = _stats_block(p)
    prompt = f"{block}\n\nVad var sämst? Nämn stat med störst gap mot PGA Tour-snittet. Svar:"
    for tmpl in BAD_COMPLETIONS[:5]:
        examples.append({"format": "B", "prompt": prompt, "completion": _fill(tmpl, p)})
    # add more variation
    wk = _weakness(p)
    for tmpl in BAD_COMPLETIONS:
        examples.append({"format": "B", "prompt": prompt, "completion": _fill(tmpl, p)})

# Format C — TipStep (~40 examples)
for p in PROFILES:
    wk = _weakness(p)
    tips_for_wk = TIPS[wk]
    # build a bad-sentence to use as prefix
    bad_templates = BAD_COMPLETIONS[:2]
    for bad_tmpl in bad_templates:
        bad_sentence = _fill(bad_tmpl, p)
        tip_prompt = f"Spelaren har {bad_sentence}. Ge ett konkret träningstips. Svar:"
        for tip in tips_for_wk:
            examples.append({"format": "C", "prompt": tip_prompt, "completion": tip})

# Deduplicate and shuffle
seen = set()
unique = []
for ex in examples:
    key = (ex["prompt"], ex["completion"])
    if key not in seen:
        seen.add(key)
        unique.append(ex)

random.shuffle(unique)

# Strip 'format' key from output
output = [{"prompt": e["prompt"], "completion": e["completion"]} for e in unique]

split = int(len(output) * 0.8)
train, val = output[:split], output[split:]

Path("data").mkdir(exist_ok=True)
Path("data/chat_train.jsonl").write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in train), encoding="utf-8"
)
Path("data/chat_val.jsonl").write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in val), encoding="utf-8"
)

print(f"Generated {len(train)} train + {len(val)} val examples")
print("  data/chat_train.jsonl")
print("  data/chat_val.jsonl")
