"""Genererar träningsdata för Exp 8 — Fine-tuning med LoRA.

210 hårdkodade svenska golfyttranden (70 per klass) sparas som
data/train.jsonl (168 ex.) och data/val.jsonl (42 ex.) i 80/20-split.

Designprinciper:
  - Inga av de 10 testyttrandena från Exp 3–7 är med.
  - Varje klass täcker flera ordformer: nyckelord FINNS men är inte
    ensamma bärare av klassen (modellen tvingas lära sig semantik).
  - Klassbalans: exakt 70 exempel per klass.

Usage:
  uv run python generate_training_data.py
"""

import json
import os
import random

EXAMPLES = {
    "putt": [
        # Direktträffar / rak linje
        "En och en halv meter rakt mot flaggan, rullade in.",
        "Halvmetersputt, ingen rörelse, rakt i.",
        "Exakt linje, bollen försvann ner i hålet.",
        "Perfekt tempo, rullde in från tre meter.",
        "Slog en rak tvåmeters puttlinje, in.",
        "Bollen rullade längs kanten och föll in.",
        "Knappast ett slag, bara en lätt knuff in.",
        "Lugn rörelse, bollen gled sakta in i koppen.",
        "Läste läppen rätt, gick in med sista kransen.",
        "Rakaste puttsträckan jag haft, rakt i.",
        # Missar
        "Missade en meter till höger, stannade utanför.",
        "Kantträff, snurrade runt och stannade vid kanten.",
        "Lipped out precis vid hålet, otur.",
        "Lite för hårt, rullade förbi med en halvmeter.",
        "Läste brejket fel, gick åt vänster om hålet.",
        "Nästan in, stannade centimetrarna ovanför hålet.",
        "Tre centimeter för kort, stannade framför.",
        "Slog för hårt, rullade en meter förbi.",
        "Missade på vänster sida med ett finger.",
        "Glänste av kanten, studsa bort.",
        # Långa puttar
        "Tio meters lång puttlinje, landade halvmeter förbi.",
        "Lagputtade upp mot hålet, stannade nära.",
        "Lång putt från bakre kant, rullade förbi med en meter.",
        "Åtta meter nedför sluttningen, stannade vid hålet.",
        "Bollen kom rullandes hela vägen från överkanten.",
        "Tvingades laga en sex meters puttlinje.",
        "Slog en stor curver från nio meter.",
        "Lyckades lasa in en sju meters putt.",
        "Vågade sig på en lång nedförsputtning.",
        "Femton meter rakt nedför, stannade en meter kort.",
        # Tvåputtar
        "Tvåputtade från fyra meter.",
        "Behövde två försök, lyckades på andra.",
        "Tog två puttar för att avsluta hålet.",
        "Parkerade nästa och tvåputtade.",
        "Landar nära och tvåputtar in.",
        # Specifika situationer
        "Birdieputtlinje som krävde perfekt timing.",
        "Puttade för eagle, rullade in.",
        "Sista putten för par, lugn rörelse.",
        "Räddade birdien med en bra puttlinje.",
        "Bogey putt från halvmeters håll.",
        "Trejde puttlinje för den här rundan, lyckades.",
        "Puttade uppför backen, bollen stannade nära.",
        "Bollen rullade sakta in längs kanten av greenen.",
        "Snabb green, bollen sköt iväg mer än väntat.",
        "Långsam green, behövde mer kraft än beräknat.",
        # Känsla och tempo
        "Slog för mjukt, bollen dog halvvägs.",
        "Lite för hårt slagit, rullade förbi.",
        "Bra tempo på puttsträckan, rullde precis in.",
        "Solidt slag, boll rullar rakt mot hålet.",
        "Rent slag, bra rullning hela vägen.",
        "Tempo var perfekt, stannade rätt vid hålet.",
        "Kände sig bra redan i slaget, bollen gick in.",
        "Lite tveksam, men rullade ändå in.",
        "Kände fint grepp och slog en ren puttlinje.",
        "Handen skakade lite, men bollen gick in ändå.",
        # Läslinjning och brejk
        "Las brejket rätt men slog för mjukt.",
        "Brejket var mer än jag trodde, gick åt sidan.",
        "Dubbelt brejk, svår linje att läsa.",
        "Nedförsputtning med högerläpp, krävde tålamod.",
        "Uppförsputtning mot vinden, behövde mer kraft.",
        "Greenen var ojämn, bollen studsa av kursen.",
        "Kanten av greenen lutar bort från hålet.",
        "Hittade brejket perfekt, bollen svängde in.",
        "Underskattade sluttningen, gick rakt förbi.",
        "Överskattade brejket, tog fel håll.",
    ],
    "chip": [
        # Bunkerslag
        "Chippade ur bunkern och landade på greenen.",
        "Sandskott ur greensidesandgropen, boll stannade nära.",
        "Slog ur sanden, bollen flög upp och landade mjukt.",
        "Krafsade ur bunkern, för lite sand, bollen gick för långt.",
        "Tog för mycket sand, bollen dog i bunkerkanten.",
        "Perfekt sandsparv ur greenside bunkern.",
        "Bunkerskott med öppen face, bollen tog bakspin.",
        "Slog lite tjockt ur sanden, kom upp lite kort.",
        "Fin bunkerexit, bollen rullade mot hålet.",
        "Djup bunker, behövde lyfta bollen högt.",
        # Chip från rough kring green
        "Chippade ur ruffen nära greenen.",
        "Lågchip mot hålet, stannade halvmeter bort.",
        "Kort chip från kanten av greenen, rullde mot hålet.",
        "Chippade från rough, bollen landade på greenen.",
        "Chip ur tjockt gräs utanför greenen.",
        "Halvt nedgrävt i ruffen, chippade upp bra.",
        "Enkel chip från fairway-kanten mot greenen.",
        "Bollen låg i tjockt greensidegräs, chippade ut.",
        "Lågchip mot flaggan, lite för hårt, rullade förbi.",
        "Chippade upp fran nedförsluttning utanför greenen.",
        # Pitchslag
        "Pitchade upp från 30 meter, landade mjukt.",
        "Pitschade fran rough med hög boll, stannade nara.",
        "Pitch shot mot flaggan, en meter fran halet.",
        "Pitchade med lob-wedge, bollen tog lite bakspin.",
        "Halvpitch fran 20 meter, landade och stannade.",
        "Pitchade for langt, rullade over greenen.",
        "Bra pitch fran nedforsluttning, landade nara.",
        "Kort pitch med oppet klubbhuvud, hog boll.",
        "Pitchade fran sand utanfor greenen, in pa greenen.",
        "Pitchade fran runt green, stannade halvmeter bort.",
        # Wedgeslag kring green
        "Wedgeslag fran rough, bollen tog bakspin pa greenen.",
        "Sandwedge fran tjockt gras, kort avstand.",
        "Gap wedge fran 40 meter, landade mjukt.",
        "Lobwedge over hindrande rad, stannade nara.",
        "Anvande pitching wedge for en liten chip.",
        "Slog med 9-jarn som chippingjarn, rullde langs greenen.",
        "Lob wedge fran gronsidebunkern, hog bana.",
        "52-gradare fran 25 meter, perfekt avstand.",
        "56-gradare fran rough, boll stannade nara flaggan.",
        "60-gradare, hog och kort, landade mjukt och stannade.",
        # Chippingtekniker
        "Slog en bump-and-run mot greenen.",
        "Lata bollen rulla langs greenytan mot halet.",
        "Chippade med litet gungslag, ren kontakt.",
        "Studsade in pa greenen fran hardpack.",
        "Bollen studsade pa greenkanten och rullade in.",
        "Tonade bollen lite, boll flög med låg bana.",
        "Slog med öppen face för mer höjd.",
        "Kompakt swing, bra kontakt med bollen.",
        "Latt chip med avkopplad handled.",
        "Stiff-wristed chip for battre kontroll.",
        # Specifika situationer
        "Chip fran nedgraven lie, svart att fa upp bollen.",
        "Slog fran nedforsluttning utanfor greenen.",
        "Boll lag i divot, chippade upp trots laget.",
        "Chip fran tjockt ruff mot en snabb green.",
        "Chippade fran kanten av vattenhindret.",
        "Chip fran gras med mycket fukt, bollen sladdade.",
        "Chippade fran ett ojamnt underlag nara greenen.",
        "Boll lag i kant av greenside rough.",
        "Chip med bollen under fotterna pa sluttning.",
        "Lag lie i tjockt gras, behövde mer kraft.",
        # Resultat
        "Bra chip, bollen stannade en meter fran halet.",
        "Chip in for birdie, bollen gick rakt i halet.",
        "Nastan chip in, stannade vid kanten.",
        "Chip som rullade forbi halet med en meter.",
        "Okej chip, tvaputtade sedan fran nara hall.",
    ],
    "fullslag": [
        # Driverslag
        "Bra drive langt ner pa mitten av fairway.",
        "Slog en lang drive, bollen landade i fairway.",
        "Driver fran tee, bollen flög langt och rakt.",
        "Riktigt langt utslag fran tee, bra position.",
        "Driven landade i mitten, perfekt utgangslage.",
        "Slog driver, bollen gick anat an tankt, hamnade i rough.",
        "Liten krakning med drivern, bollen svangde anat.",
        "Langt utslag men hamnade i rough pa hoger sida.",
        "Slog lite under bollen med drivern, korta drive.",
        "Lang och rak drive, hittade fairway.",
        # Jarnslag
        "Tog ett 7-jarn mot greenen fran 150 meter.",
        "Slog ett 6-jarn, bollen landade pa greenen.",
        "5-jarnslag mot par 4-greenen.",
        "Mitt-jarnslag mot flaggan, 160 meter.",
        "Tog ett langt jarn fran rough.",
        "8-jarn fran 130 meter, nara flaggan.",
        "Slog ett jarnslag over vattenhindret.",
        "Lang jarnslag fran fairway, boll pa greenen.",
        "Slog ett 4-jarn mot par 3-tee.",
        "Korts jarn fran 100 meter, landade pa greenen.",
        # Tredjestick / inkommande jarnslag
        "Inkommande till greenen med ett kort jarn.",
        "Tredje slaget mot en par 5-green.",
        "Approachslag med 9-jarnet fran 120 meter.",
        "Lagrade in mot greenen med ett mellanjarn.",
        "Approachade med pitching wedge fran 100 meter.",
        "Slog ett mellanjarnslag fran fairway bunker.",
        "Bra inkommande med en hybrid fran 180 meter.",
        "Tredje slaget pa par 5, nara flaggan.",
        "Approachslag som landade nara halet.",
        "Tog ett langt jarn fran svart lie i rough.",
        # Hybrid och fairwaywood
        "Slog en hybrid fran fairway, 200 meter.",
        "Fairwaywood mot par 5-greenen i tva.",
        "Hybrid fran rough, boll landade kort fran green.",
        "3-wood fran tee pa ett kort par 4.",
        "Slog en hybrid over bunker mot greenen.",
        "5-wood fran fairway, boll pa kanten av greenen.",
        "Hybridslag pa uppforsluttning, bra treff.",
        "Langt slag med 3-wood, hittade fairway.",
        "Hybridslag mot par 3 fran 190 meter.",
        "Slog ett fairwaywood ur rough.",
        # Par 3
        "Teeskott pa par 3 med 7-jarn, boll pa greenen.",
        "Slog ett 8-jarn mot par 3-flaggan.",
        "Par 3 med vind, tog ett langre jarn.",
        "Teeskott pa det korta par 3, nara halet.",
        "Slog ett mellanjarn pa par 3, 150 meter.",
        "Par 3 teeskott, boll landade en meter fran halet.",
        "Slog med 6-jarn pa ett langt par 3.",
        "Teeskott med hybrid pa ett 190 meters par 3.",
        "Par 3 fran hog tee, tog ett kortare jarn an vanligt.",
        "Slog med pitching wedge pa det korta par 3.",
        # Slagsituationer
        "Slog ett raddningsslag fran rough till fairway.",
        "Slog ur greenside rough med ett langt jarn.",
        "Fullslag over traden mot fairway.",
        "Slog fran fairway bunker med ett jarn.",
        "Provade en hybrid fran djup rough.",
        "Slog under traden med ett latt jarn.",
        "Spela runt hindret med ett krökt slag.",
        "Slog ett slag fran bakvattnet utanfor.",
        "Fint angreppssatt fran trång lie.",
        "Slog ett rengt slag trots svart underlag.",
        # Resultat
        "Bollen landade pa greenen, nara flaggan.",
        "Missade greenen till hoger.",
        "Slog over greenen, hamnade bakom.",
        "Boll pa greenen, 6 meter fran halet.",
        "Traffade en bunker med inkommande slag.",
        "Missade till vanster, boll i rough.",
        "Landade pa greenen men rullde av bakre kant.",
        "Boll pa greenen, bra lage for birdie.",
        "Hamnade precis pa kanten av greenen.",
        "Hittade greenen fran 170 meter, solidt slag.",
    ],
}

# Sanity-check: ingen testexempel ska finnas i träningsdatan
TEST_UTTERANCES = {
    "Tre meter rakt mot halet, rullde in.",
    "Kort putt, missade till hoger.",
    "Rullning in fran kanten, precis.",
    "Lagchip mot flaggan, stannade en meter bort.",
    "Chippade ur bunkern, landade pa greenen.",
    "Sandwedge fran rough, studsade forbi.",
    "Bra drive langt ner mitten.",
    "Tog ett jarnslag mot par 3-halet.",
    "7-jarn mot greenen, lite for lang.",
    "Slog en wedge, bollen landade nara flaggan.",
}


def build_dataset() -> list[dict]:
    rows = []
    for label, utterances in EXAMPLES.items():
        for u in utterances:
            assert u not in TEST_UTTERANCES, f"Testyttrande läckte in i träningsdata: {u}"
            rows.append({"utterance": u, "label": label})
    return rows


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    random.seed(42)
    rows = build_dataset()

    # Stratifierad split — 80/20 per klass
    train, val = [], []
    for label in EXAMPLES:
        group = [r for r in rows if r["label"] == label]
        random.shuffle(group)
        split = int(len(group) * 0.8)
        train.extend(group[:split])
        val.extend(group[split:])
    random.shuffle(train)
    random.shuffle(val)

    os.makedirs("data", exist_ok=True)
    write_jsonl("data/train.jsonl", train)
    write_jsonl("data/val.jsonl", val)

    counts = lambda lst: {k: sum(1 for r in lst if r["label"] == k) for k in EXAMPLES}
    print(f"Träning : {len(train)} exempel  {counts(train)}")
    print(f"Val     : {len(val)} exempel  {counts(val)}")
    print(f"Totalt  : {len(rows)} exempel")
    print(f"\nSparat  : data/train.jsonl, data/val.jsonl")


if __name__ == "__main__":
    main()
