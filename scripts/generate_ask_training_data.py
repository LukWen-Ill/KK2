"""Genererar träningsdata för /ai/ask CoT-pipelinen (Exp 9 fine-tuning).

Lärdomar från Exp 8 (slagtypsklassificering) tillämpade här:
  - ~100–150 ex per deluppgift räcker; kvalitet slår kvantitet.
  - Matcha exakt det prompt-format som modellen möter vid inferens.
  - Variera indata (spelarprofiler, frågor) för att undvika överanpassning
    till en specifik spelares siffror.
  - Uteslut de 20 testfrågorna ur träningsdatan.

Tre typer av exempel (alla engelska, matchar steps.py):

  A. WeaknessStep  — "Complete in one short phrase: 'Low {stat} means the player...'"
  B. ImpactStep    — "One phrase connecting the weakness to this question:"
  C. AskAnswerComposerStep — full JSON {stat, player_value, pga_value, advice}
     (advice måste innehålla drill-referens för att passera eval-kategorin
     "Stats + drill (OK)")

Utdata: data/ask_train.jsonl (80 %) + data/ask_val.jsonl (20 %)
Format: {"prompt": "...", "completion": "..."} — samma som chat_train.jsonl
och kompatibelt med run_chat_finetune.py.

Usage:
  uv run python scripts/generate_ask_training_data.py
"""

import json
import os
import random

random.seed(42)

# ---------------------------------------------------------------------------
# Konstanter
# ---------------------------------------------------------------------------
PGA = {
    "gir_pct": 65.0,
    "fairway_pct": 60.0,
    "avg_putts": 1.73,
    "scoring_avg": 3.92,   # per hole
}

# De 20 testfrågorna — inga av dessa får finnas i träningsdatan
TEST_QUESTIONS = {
    "What is my biggest weakness?",
    "How can I improve my scoring?",
    "What should I practice first?",
    "Why am I missing so many greens?",
    "How do I lower my handicap?",
    "Am I a good putter compared to pros?",
    "What drill should I do for GIR?",
    "How far am I from PGA Tour level?",
    "Is my fairway accuracy good or bad?",
    "What one thing would help me most?",
    "How can I reduce my putts per hole?",
    "My GIR is low — what causes that?",
    "What's my strongest stat?",
    "How many more greens do pros hit?",
    "Should I focus on putting or approach shots?",
    "How does my scoring compare to scratch golfers?",
    "What practice routine would improve my game fastest?",
    "I'm struggling with approach shots. What drill helps?",
    "What does my GIR percentage tell about my iron play?",
    "Give me one concrete tip based on my stats.",
}

# Spelarprofiler: (gir_pct, fairway_pct, avg_putts, scoring_avg_per_hole)
PROFILES = [
    (10, 35, 3.0, 6.5),
    (15, 42, 2.8, 6.0),
    (22, 48, 2.5, 5.8),
    (28, 52, 2.3, 5.5),
    (35, 57, 2.2, 5.1),
    (42, 61, 2.1, 4.9),
    (50, 65, 2.0, 4.6),
    (58, 68, 1.9, 4.3),
    (65, 72, 1.8, 4.1),
    (72, 78, 1.75, 3.9),
]

# Drills hämtade ur _DRILL_DB i steps.py (används i completion-texten)
DRILLS = {
    "GIR": "9-shot drill: hit three balls each from 100, 150, and 200 yards aiming at green center.",
    "Fairway": "Alignment stick drill: lay a stick along your target line and rehearse takeaway staying parallel.",
    "Putts": "Gate putting drill: place two tees 1 inch wider than your putter face, 3 feet from hole — make 20 consecutive putts.",
    "Scoring": "Par-3 challenge: play only par-3 holes for a full round, target par or better on every hole.",
}


def _gap_str(stat: str, profile: tuple) -> str:
    gir, fw, putts, scoring = profile
    if stat == "GIR":
        return f"{gir}% vs PGA avg {PGA['gir_pct']:.1f}%"
    if stat == "Fairway":
        return f"{fw}% vs PGA avg {PGA['fairway_pct']:.1f}%"
    if stat == "Putts":
        return f"{putts} vs PGA avg {PGA['avg_putts']}"
    # Scoring
    return f"{scoring}/hole vs PGA avg {PGA['scoring_avg']:.2f}/hole"


def _player_value(stat: str, profile: tuple) -> float:
    gir, fw, putts, scoring = profile
    return {
        "GIR": float(gir),
        "Fairway": float(fw),
        "Putts": putts,
        "Scoring": scoring,
    }[stat]


def _pga_value(stat: str) -> float:
    return {
        "GIR": PGA["gir_pct"],
        "Fairway": PGA["fairway_pct"],
        "Putts": PGA["avg_putts"],
        "Scoring": PGA["scoring_avg"],
    }[stat]


# ---------------------------------------------------------------------------
# A. WeaknessStep-exempel
# Prompt matchar exakt WeaknessStep.invoke() i steps.py.
# ---------------------------------------------------------------------------

WEAKNESS_COMPLETIONS = {
    "GIR": [
        "struggles to reach greens in regulation, leading to more difficult up-and-downs.",
        "often misses greens and must rely on chipping and putting to save par.",
        "hits fewer greens than needed, creating pressure on the short game.",
        "frequently approaches from rough or bunkers instead of the fairway.",
        "lacks iron precision, resulting in scrambling situations on most holes.",
        "reaches greens less often than pros, making birdie opportunities rare.",
    ],
    "Fairway": [
        "often drives into rough, reducing approach shot options and accuracy.",
        "starts holes from disadvantaged positions, increasing scoring difficulty.",
        "loses distance and control from rough, leading to longer approaches.",
        "hits fewer fairways than pros, which cascades into weaker approach shots.",
        "faces harder lies on most tee shots, making precise iron play difficult.",
        "misses fairways more than pros, costing valuable approach angles.",
    ],
    "Putts": [
        "takes too many strokes on the green, costing shots every round.",
        "wastes scoring opportunities by three-putting from makeable distances.",
        "loses shots after reaching the green due to poor putting consistency.",
        "averages more putts per hole than the PGA Tour, adding strokes needlessly.",
        "struggles to convert birdie opportunities into actual birdies.",
        "spends an extra stroke on the green compared to tour professionals.",
    ],
    "Scoring": [
        "scores significantly above the PGA Tour average per hole.",
        "gives away strokes throughout the round compared to scratch golfers.",
        "accumulates more shots per hole than professional-level benchmarks.",
        "overshoots par on most holes, indicating widespread inefficiency.",
        "scores at an amateur pace with room to improve across all stats.",
        "averages more than one shot above pros per hole across the round.",
    ],
}


def build_weakness_examples() -> list[dict]:
    """4 stats × 10 profiles × 6 completions = 240 examples."""
    rows = []
    for stat, completions in WEAKNESS_COMPLETIONS.items():
        for profile in PROFILES:
            gap = _gap_str(stat, profile)
            prompt = (
                f"Golf stat: {stat} is {gap}.\n"
                f"Complete in one short phrase: 'Low {stat} means the player...'\n"
                "Answer:"
            )
            for c in completions:
                rows.append({
                    "type": "A_weakness",
                    "prompt": prompt,
                    "completion": f"Low {stat} means the player {c}",
                })
    return rows


# ---------------------------------------------------------------------------
# B. ImpactStep-exempel
# Prompt matchar exakt ImpactStep.invoke() i steps.py.
# ---------------------------------------------------------------------------

# Training questions (avoids the 20 test questions)
TRAIN_QUESTIONS = [
    "What area of my game needs the most attention?",
    "Which stat is holding back my scorecard?",
    "How should I spend my practice time?",
    "What is preventing me from shooting lower scores?",
    "Which weakness hurts my round the most?",
    "How can I break 90 / 80 more consistently?",
    "What part of my game costs me the most strokes?",
    "Where do I lose the most shots compared to pros?",
    "What one change would have the biggest impact on my score?",
    "Which stat should I work on before my next competition?",
    "How much better could my score be if I fixed my main weakness?",
    "What is stopping me from reaching my handicap goal?",
    "Does my approach game need work?",
    "Am I spending my practice time on the right things?",
    "What would a coach tell me to improve first?",
]

IMPACT_COMPLETIONS: dict[str, dict[str, str]] = {
    "GIR": {
        "What area of my game needs the most attention?":
            "Your GIR at {gap} is the primary area needing attention — iron play drives nearly all other stats.",
        "Which stat is holding back my scorecard?":
            "Your GIR of {gap} is the main scorecard liability — missing greens creates costly recovery situations.",
        "How should I spend my practice time?":
            "With GIR at {gap}, iron and approach shot practice should dominate your sessions.",
        "What is preventing me from shooting lower scores?":
            "GIR at {gap} is the barrier — not reaching greens in regulation forces hard up-and-downs.",
        "Which weakness hurts my round the most?":
            "GIR at {gap} hurts your round the most — missed greens multiply your stroke count.",
        "How can I break 90 / 80 more consistently?":
            "Improving your GIR from {gap} toward the 65% pro average is the fastest path to lower scores.",
        "What part of my game costs me the most strokes?":
            "Your GIR at {gap} costs the most strokes — every missed green is a potential bogey or worse.",
        "Where do I lose the most shots compared to pros?":
            "You lose the most shots on approach — GIR at {gap} compared to the pro standard.",
        "What one change would have the biggest impact on my score?":
            "Improving GIR from {gap} would have the single biggest impact on your scorecard.",
        "Which stat should I work on before my next competition?":
            "GIR at {gap} is the highest-priority stat before competition — better approach shots lower risk.",
        "How much better could my score be if I fixed my main weakness?":
            "Lifting GIR from {gap} toward 65% could save 3–6 strokes per round.",
        "What is stopping me from reaching my handicap goal?":
            "GIR at {gap} is the biggest handicap barrier — missing greens forces scrambling on nearly every hole.",
        "Does my approach game need work?":
            "Yes — GIR at {gap} shows that approach shots are significantly below tour standard.",
        "Am I spending my practice time on the right things?":
            "Probably not if GIR is at {gap} — approach shot practice should be your top priority.",
        "What would a coach tell me to improve first?":
            "A coach would point directly to GIR at {gap} as the first priority — it affects every hole.",
    },
    "Fairway": {
        "What area of my game needs the most attention?":
            "Fairway accuracy at {gap} is the area needing most attention — poor tee shots cascade into harder approaches.",
        "Which stat is holding back my scorecard?":
            "Fairway at {gap} is dragging down your scorecard — rough lies make everything harder.",
        "How should I spend my practice time?":
            "With fairway at {gap}, driver accuracy and controlled tee shots should be your practice focus.",
        "What is preventing me from shooting lower scores?":
            "Fairway at {gap} is a key barrier — starting holes from rough limits your approach options.",
        "Which weakness hurts my round the most?":
            "Fairway at {gap} creates trouble early on each hole, setting up a cascade of extra shots.",
        "How can I break 90 / 80 more consistently?":
            "Getting fairway from {gap} closer to 60% would consistently lower your starting position.",
        "What part of my game costs me the most strokes?":
            "Fairway at {gap} costs strokes indirectly — rough lies lead to worse approach shots and higher scores.",
        "Where do I lose the most shots compared to pros?":
            "You lose shots early — fairway at {gap} means worse position for every second shot.",
        "What one change would have the biggest impact on my score?":
            "Improving fairway from {gap} to 60%+ would ripple through your entire scorecard.",
        "Which stat should I work on before my next competition?":
            "Fairway at {gap} is the stat to address before competition — accuracy off the tee reduces risk.",
        "How much better could my score be if I fixed my main weakness?":
            "Better fairway accuracy from {gap} toward the tour average could save 2–4 strokes per round.",
        "What is stopping me from reaching my handicap goal?":
            "Fairway at {gap} is limiting you — starting from rough consistently adds strokes.",
        "Does my approach game need work?":
            "Partly — fairway at {gap} means many approach shots come from rough rather than fairway.",
        "Am I spending my practice time on the right things?":
            "Driver practice targeting fairway — currently at {gap} — would be the highest-value use of time.",
        "What would a coach tell me to improve first?":
            "A coach would target your driver first — fairway at {gap} creates problems on nearly every hole.",
    },
    "Putts": {
        "What area of my game needs the most attention?":
            "Putting at {gap} is the clearest area to improve — extra putts add up on every green.",
        "Which stat is holding back my scorecard?":
            "Putting at {gap} is a direct scorecard cost — more putts per green equals higher scores.",
        "How should I spend my practice time?":
            "With putting at {gap}, daily putting practice — especially from 3–10 feet — is most valuable.",
        "What is preventing me from shooting lower scores?":
            "Putting at {gap} is a direct obstacle — finishing holes with fewer strokes starts on the green.",
        "Which weakness hurts my round the most?":
            "Putting at {gap} hurts your round on every hole — the green is where shots are lost or saved.",
        "How can I break 90 / 80 more consistently?":
            "Reducing putts from {gap} toward 1.73 would consistently save 2–4 strokes per round.",
        "What part of my game costs me the most strokes?":
            "Putting at {gap} adds the most direct strokes — every extra putt per hole is a direct score cost.",
        "Where do I lose the most shots compared to pros?":
            "You lose shots on the green — putting at {gap} compared to the tour's 1.73 average.",
        "What one change would have the biggest impact on my score?":
            "Reducing putting from {gap} is the single highest-leverage change for your scorecard.",
        "Which stat should I work on before my next competition?":
            "Putting at {gap} is the most immediate stat to address — it impacts every hole directly.",
        "How much better could my score be if I fixed my main weakness?":
            "Cutting putts from {gap} to near 1.73 could save 3–8 strokes per round.",
        "What is stopping me from reaching my handicap goal?":
            "Putting at {gap} is a consistent handicap drag — every extra putt adds directly to your score.",
        "Does my approach game need work?":
            "Your approach game may be fine — putting at {gap} is where the shots are actually being lost.",
        "Am I spending my practice time on the right things?":
            "Not if you skip the putting green — {gap} means significant strokes are being lost there.",
        "What would a coach tell me to improve first?":
            "A coach would prioritize putting — at {gap}, it is the most direct and measurable area to improve.",
    },
    "Scoring": {
        "What area of my game needs the most attention?":
            "Overall scoring at {gap} reflects widespread inefficiency — multiple stats need addressing.",
        "Which stat is holding back my scorecard?":
            "Scoring at {gap} shows the combined effect of all weaknesses holding back your rounds.",
        "How should I spend my practice time?":
            "With scoring at {gap}, focus on eliminating bogeys and double-bogeys through strategic play.",
        "What is preventing me from shooting lower scores?":
            "Scoring at {gap} means your overall course management and execution need improvement.",
        "Which weakness hurts my round the most?":
            "Scoring at {gap} indicates consistent losses throughout — no single stat explains it all.",
        "How can I break 90 / 80 more consistently?":
            "Getting scoring from {gap} down requires eliminating avoidable mistakes on every hole.",
        "What part of my game costs me the most strokes?":
            "Overall scoring at {gap} reflects strokes lost throughout — identify your worst holes.",
        "Where do I lose the most shots compared to pros?":
            "Scoring at {gap} shows you give away shots across all aspects of your game.",
        "What one change would have the biggest impact on my score?":
            "Avoiding double-bogeys — which scoring at {gap} suggests are frequent — would help most.",
        "Which stat should I work on before my next competition?":
            "Scoring at {gap} indicates the need for focused course management and risk reduction.",
        "How much better could my score be if I fixed my main weakness?":
            "Improving from {gap} toward scratch level requires consistent execution across all stats.",
        "What is stopping me from reaching my handicap goal?":
            "Scoring at {gap} is the target — your goal is to reduce this through improvement in all areas.",
        "Does my approach game need work?":
            "Likely — scoring at {gap} often traces back to poor approach shots creating difficult up-and-downs.",
        "Am I spending my practice time on the right things?":
            "With scoring at {gap}, review your scorecard patterns — identify the holes losing the most shots.",
        "What would a coach tell me to improve first?":
            "A coach would analyze your scorecard pattern — scoring at {gap} often hides a clear repeating error.",
    },
}


def build_impact_examples() -> list[dict]:
    """4 stats × 10 profiles × 15 questions = 600 examples (all combos)."""
    weakness_descs = {
        "GIR": "Low GIR means the player frequently misses greens, requiring difficult up-and-downs.",
        "Fairway": "Low Fairway means the player often drives into rough, reducing approach options.",
        "Putts": "Low Putts means the player takes too many strokes on the green each round.",
        "Scoring": "Low Scoring means the player scores significantly above the PGA Tour average per hole.",
    }
    rows = []
    for stat, q_map in IMPACT_COMPLETIONS.items():
        for profile in PROFILES:
            gap = _gap_str(stat, profile)
            weakness_desc = weakness_descs[stat]
            for q, completion_template in q_map.items():
                assert q not in TEST_QUESTIONS, f"Test question leaked: {q}"
                completion = completion_template.replace("{gap}", gap)
                prompt = (
                    f"Weakness: {stat} {gap}. {weakness_desc}\n"
                    f"Question: {q}\n"
                    "One phrase connecting the weakness to this question: Answer:"
                )
                rows.append({"type": "B_impact", "prompt": prompt, "completion": completion})
    return rows


# ---------------------------------------------------------------------------
# C. AskAnswerComposerStep-exempel
# Prompt matchar AskAnswerComposerStep.invoke() i steps.py.
# Completion = valid JSON med advice som refererar till drill-texten.
# Detta tränar modellen att inkludera drill-ord i advice-fältet, vilket
# förbättrar eval-kategorin "Stats + drill (OK)".
# ---------------------------------------------------------------------------

ADVICE_TEMPLATES = {
    "GIR": [
        "Focus your practice on approach shots — try the 9-shot drill from 100, 150, and 200 yards to build green-finding consistency.",
        "Your iron play needs the most work. Use the 9-shot drill: hit three balls from 100, 150, and 200 yards toward green center daily.",
        "Hit the range and practice the 9-shot approach drill — reaching more greens in regulation will lower your score directly.",
        "Work on approach shot accuracy with the 9-shot drill; landing on more greens eliminates scrambling and saves strokes.",
    ],
    "Fairway": [
        "Practice controlled tee shots with the alignment stick drill — lay a stick along your target line and rehearse takeaway.",
        "Use the alignment stick drill to improve driver accuracy; hitting more fairways gives better angles for every second shot.",
        "Run the alignment stick drill daily to groove a repeatable takeaway — fairway accuracy is the foundation of consistent scoring.",
        "Focus driver practice on path and alignment; the stick drill trains a repeatable swing before adding distance.",
    ],
    "Putts": [
        "Set up the gate putting drill — two tees 1 inch wider than your putter, 3 feet from the hole, and make 20 putts in a row.",
        "Practice the gate putting drill consistently to improve stroke path — reducing three-putts from this range saves strokes immediately.",
        "Use the gate drill to train a square face at impact; eliminating one three-putt per round can drop your score significantly.",
        "Daily gate putting practice from 3–6 feet trains the most common missed putt distance and improves consistency.",
    ],
    "Scoring": [
        "Play the par-3 challenge: dedicate a practice round to par-3 holes only, targeting par or better on each — sharpens course management.",
        "Try the par-3 scramble drill to train scoring decisions under pressure; smart play on these holes transfers to your full round.",
        "Use the par-3 challenge to practice strategic shot selection — eliminating doubles on easy holes cuts your scoring average.",
        "Focus practice rounds on par-3 play; the par-3 challenge builds the decision-making skills that lower overall scoring.",
    ],
}


def build_composer_examples() -> list[dict]:
    """4 stats × 10 profiles × 4 advice variants × 15 questions = 2400.
    Vi begränsar till 4 stats × 10 profiles × 4 advices = 160 ex för att
    undvika att dominera träningsdatan (ImpactStep har fler varianter).
    Frågan roteras per profil för variation utan att testfrågor läcker in."""
    weakness_descs = {
        "GIR": "Low GIR means the player frequently misses greens, requiring difficult up-and-downs.",
        "Fairway": "Low Fairway means the player often drives into rough, reducing approach options.",
        "Putts": "Low Putts means the player takes too many strokes on the green each round.",
        "Scoring": "Low Scoring means the player scores significantly above the PGA Tour average per hole.",
    }
    train_qs = [q for q in TRAIN_QUESTIONS if q not in TEST_QUESTIONS]
    rows = []
    for stat in ("GIR", "Fairway", "Putts", "Scoring"):
        advice_list = ADVICE_TEMPLATES[stat]
        for profile in PROFILES:
            gap = _gap_str(stat, profile)
            pv = _player_value(stat, profile)
            pgav = _pga_value(stat)
            drill = DRILLS[stat]
            weakness_desc = weakness_descs[stat]
            for ai, advice in enumerate(advice_list):
                question = train_qs[(len(rows) + ai) % len(train_qs)]
                prompt = (
                    f"Golf coach. Player's worst stat: {stat} at {gap}.\n"
                    f"Weakness: {weakness_desc}\n"
                    f"Drill: {drill}\n"
                    f"Question: {question}\n"
                    "Output JSON with stat, player_value, pga_value, advice:"
                )
                completion = json.dumps(
                    {
                        "stat": stat,
                        "player_value": pv,
                        "pga_value": pgav,
                        "advice": advice,
                    },
                    ensure_ascii=False,
                )
                rows.append({"type": "C_composer", "prompt": prompt, "completion": completion})
    return rows


# ---------------------------------------------------------------------------
# Sätt ihop, deduplicera, dela upp
# ---------------------------------------------------------------------------

def main() -> None:
    all_examples = (
        build_weakness_examples()
        + build_impact_examples()
        + build_composer_examples()
    )

    # Verifiera att inga testfrågor läckt in
    for ex in all_examples:
        for q in TEST_QUESTIONS:
            assert q not in ex["prompt"], f"Test question in prompt: {q}"

    # Stratifierad 80/20-split per typ
    train: list[dict] = []
    val: list[dict] = []
    for type_key in ("A_weakness", "B_impact", "C_composer"):
        group = [e for e in all_examples if e["type"] == type_key]
        random.shuffle(group)
        split = int(len(group) * 0.8)
        train.extend(group[:split])
        val.extend(group[split:])

    random.shuffle(train)
    random.shuffle(val)

    # Ta bort type-nyckeln ur utdata
    def strip_type(rows: list[dict]) -> list[dict]:
        return [{"prompt": r["prompt"], "completion": r["completion"]} for r in rows]

    os.makedirs("data", exist_ok=True)
    train_out = strip_type(train)
    val_out = strip_type(val)

    def write_jsonl(path: str, rows: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_jsonl("data/ask_train.jsonl", train_out)
    write_jsonl("data/ask_val.jsonl", val_out)

    def counts(lst: list[dict], key: str) -> int:
        return sum(1 for r in lst if r["type"] == key)

    print(f"A (WeaknessStep) : {counts(train, 'A_weakness'):3d} träning  {counts(val, 'A_weakness'):2d} val")
    print(f"B (ImpactStep)   : {counts(train, 'B_impact'):3d} träning  {counts(val, 'B_impact'):2d} val")
    print(f"C (ComposerStep) : {counts(train, 'C_composer'):3d} träning  {counts(val, 'C_composer'):2d} val")
    print(f"Totalt           : {len(train_out):3d} träning  {len(val_out):2d} val")
    print()
    print("Sparat: data/ask_train.jsonl, data/ask_val.jsonl")
    print()
    print("Kör träning med run_chat_finetune.py — men uppdatera sökvägarna:")
    print('  load_jsonl("data/ask_train.jsonl")')
    print('  load_jsonl("data/ask_val.jsonl")')


if __name__ == "__main__":
    main()
