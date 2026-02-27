"""
FitTracker — Flask backend
Stockage : Supabase (PostgreSQL)
Charts   : Plotly (JSON renvoyé au front, rendu via plotly.js CDN)
Deploy   : Vercel (serverless)
"""

import json, os, uuid, io
from datetime import datetime, date
from collections import defaultdict

from flask import Flask, jsonify, request, abort, render_template, send_file
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from supabase import create_client, Client

# ── SETUP ──────────────────────────────────────────────────────────────────

_BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            static_folder=os.path.join(_BASE, "static"),
            template_folder=os.path.join(_BASE, "templates"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_sb: Client = None

def sb() -> Client:
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL et SUPABASE_KEY doivent être définis.")
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── PLOTLY DARK THEME ─────────────────────────────────────────────────────

LAYOUT_BASE = dict(
    paper_bgcolor="#111118", plot_bgcolor="#111118",
    font=dict(family="Inter, sans-serif", color="#8888aa", size=12),
    margin=dict(t=50, b=40, l=50, r=30),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#1e1e2a", font_color="#f0f0f8", bordercolor="#2a2a38"),
    legend=dict(bgcolor="#16161f", bordercolor="#2a2a38", borderwidth=1,
                font=dict(color="#c0c0d0", size=11)),
    colorway=["#e94560","#00d4ff","#ffd740","#00e676","#c792ea","#ff6b6b","#82aaff"],
)
AXIS_STYLE = dict(gridcolor="#2a2a38", linecolor="#2a2a38",
                  tickfont=dict(color="#8888aa"), zerolinecolor="#2a2a38")

def new_id():
    return str(uuid.uuid4())[:8]

def get_week_key(date_str):
    d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ── SEED DATA ──────────────────────────────────────────────────────────────

EXERCISES_SEED = [
    ("Développé couché","Pectoraux","free_weight","Allongé sur banc plat, saisissez la barre en prise large. Descendez jusqu'à effleurer la poitrine, poussez verticalement en contractant les pectoraux. Omoplates rétractées, dos légèrement cambré.","Serrez la barre comme si vous vouliez la casser. Expirez à la poussée.","Triceps, Deltoïdes antérieurs",192),
    ("Développé incliné haltères","Pectoraux","free_weight","Banc incliné à 30-45°, coudes à ~75° du torse. Descendez jusqu'à l'étirement des pecs supérieurs, poussez en arc.","Ne pas monter le banc au-delà de 45°. Cible le haut des pecs.","Triceps, Épaules antérieures",314),
    ("Écarté haltères","Pectoraux","free_weight","Allongé sur banc, ouvrez les bras en arc jusqu'à l'étirement des pecs, ramenez en contractant fort. Coudes légèrement fléchis.","Poids modéré, concentration sur la contraction. Isolation pure.","Biceps (stabilisation)",119),
    ("Pec Deck Machine","Pectoraux","machine","Coudes et avant-bras contre les coussinets. Ramenez vers le centre en contractant, marquez une pause, revenez lentement.","Régler le siège pour que les coudes soient à hauteur d'épaule.","Épaules antérieures",0),
    ("Chest Press Machine","Pectoraux","machine","Dos bien appuyé, poignées à hauteur de poitrine. Poussez en contractant les pecs, revenez lentement.","Tension constante tout au long du mouvement.","Triceps, Épaules",0),
    ("Cable Crossover","Pectoraux","machine","Poulies hautes, légère inclinaison vers l'avant. Amenez les câbles vers le bas et l'intérieur en croisant les mains. Retour lent.","La poulie maintient une tension constante sur tout le mouvement.","Épaules antérieures, Biceps",0),
    ("Dips","Pectoraux","bodyweight","Corps légèrement penché en avant. Descendez jusqu'à ce que les épaules soient sous le niveau des coudes, remontez.","Penchez-vous vers l'avant et écartez légèrement les coudes pour cibler les pecs.","Triceps, Épaules antérieures",73),
    ("Pompes","Pectoraux","bodyweight","Corps en planche rigide, mains légèrement plus larges que les épaules. Descendez la poitrine vers le sol, coudes à ~45°.","Serrez abdos et fessiers pendant tout le mouvement. Large = plus de pecs, serré = plus de triceps.","Triceps, Épaules, Abdominaux",35),
    ("Tractions","Dos","bodyweight","Suspension complète, tirez jusqu'au menton au-dessus de la barre en rétractant les omoplates. Descendez lentement.","Imaginez que vous tirez des coudes vers les hanches plutôt que de fléchir les bras.","Biceps, Rhomboïdes, Grand rond",31),
    ("Rowing haltère","Dos","free_weight","Un genou et une main sur un banc, dos plat. Tirez l'haltère vers la hanche, coude le long du corps. Descendez lentement.","Penser à mettre la main dans la poche arrière. Éviter de tourner le tronc.","Biceps, Rhomboïdes, Trapèzes",197),
    ("Soulevé de terre","Dos","free_weight","Pieds dans la largeur des hanches, dos plat. Poussez le sol et tirez la barre le long des jambes jusqu'à la station debout.","Le roi des exercices. Barre contre les tibias/cuisses. Inspirez profondément avant de tirer.","Quadriceps, Fessiers, Trapèzes, Ischio-jambiers",29),
    ("Rowing barre","Dos","free_weight","Penché à ~45°, barre en prise pronation. Tirez vers le nombril en rétractant les omoplates. Coudes vers l'arrière.","45° recrute plus le grand dorsal. Plus vertical = plus de trapèzes.","Biceps, Trapèzes, Rhomboïdes",63),
    ("Lat Pulldown","Dos","machine","Prise pronation large, tirez la barre vers le haut de la poitrine en rétractant les omoplates. Revenez bras tendus.","Inclinez légèrement le buste (10-15°). Tirez vers la clavicule, jamais derrière la nuque.","Biceps, Grand rond, Rhomboïdes",122),
    ("Rowing assis machine","Dos","machine","Poitrine contre le support. Tirez en rétractant les omoplates, revenez avec un bon étirement.","Prise serrée neutre = plus de grand dorsal. Prise large = plus de rhomboïdes.","Biceps, Rhomboïdes, Trapèzes",115),
    ("Face Pull","Dos","machine","Poulie haute avec corde. Tirez vers le visage, coudes écartés à hauteur d'épaules, tournez les poignets vers l'extérieur.","Exercice indispensable pour la santé des épaules. À faire à chaque séance pull.","Deltoïdes postérieurs, Trapèzes, Rotateurs externes",0),
    ("Développé militaire","Épaules","free_weight","Barre devant à hauteur de la clavicule. Poussez verticalement au-dessus de la tête jusqu'à extension complète. Core solide.","Rentrez le menton quand la barre passe devant le visage. Serrez les fessiers.","Triceps, Trapèzes, Dentelé antérieur",68),
    ("Élévations latérales","Épaules","free_weight","Haltères le long du corps. Levez les bras sur les côtés jusqu'à l'horizontale, légère rotation externe. Descendez lentement.","Poids léger, haute répétition. Ne pas balancer le tronc — si c'est le cas, le poids est trop lourd.","Trapèzes supérieurs",0),
    ("Élévations frontales","Épaules","free_weight","Levez les bras droit devant jusqu'à l'horizontale, descendez lentement. Isole le faisceau antérieur.","Souvent déjà bien sollicité par les développés. Poids modéré, contrôle maximal.","Pectoraux supérieurs",0),
    ("Arnold Press","Épaules","free_weight","Haltères devant le visage, paumes vers soi. En montant, tournez progressivement les paumes vers l'avant. Inversez en descendant.","La rotation implique les trois faisceaux des deltoïdes. Mouvement complet.","Triceps, Trapèzes",0),
    ("Shoulder Press Machine","Épaules","machine","Poignées à hauteur des épaules, poussez sans verrouiller les coudes, revenez lentement.","Régler le siège pour que les poignées soient à hauteur des oreilles.","Triceps, Trapèzes",0),
    ("Curl barre","Biceps","free_weight","Barre en prise supination, fléchissez les coudes vers les épaules, coudes fixes. Descendez avec résistance.","Les coudes NE bougent PAS. Contractez fort 1 seconde en haut.","Brachial, Brachio-radial",11),
    ("Curl haltères","Biceps","free_weight","Fléchissez un bras à la fois en tournant le poignet vers l'extérieur en montant (supination). Descendez lentement.","La supination maximise l'activation du biceps.","Brachial, Brachio-radial",42),
    ("Curl marteau","Biceps","free_weight","Haltères en prise neutre. Fléchissez les coudes en montant, coudes fixes.","Excellent pour épaissir le bras et renforcer les avant-bras.","Brachio-radial, Avant-bras",0),
    ("Curl poulie basse","Biceps","machine","Face à la poulie basse. Tirez vers le haut en fléchissant les coudes, tension constante.","Excellente finition. La tension constante favorise le pump.","Brachial",0),
    ("Skull Crusher","Triceps","free_weight","Allongé sur banc, barre au-dessus de la tête. Fléchissez uniquement les coudes vers le front, remontez.","Descente lente et contrôlée. Excellent pour le chef long du triceps.","Chef long du triceps",26),
    ("Extension au-dessus tête","Triceps","free_weight","Haltère au-dessus de la tête. Fléchissez les coudes pour descendre le poids derrière la tête, remontez.","Le chef long s'étire complètement avec le bras au-dessus.","Chef long du triceps",0),
    ("Dips triceps","Triceps","bodyweight","Corps vertical (pas penché), descendez jusqu'à 90° des coudes, remontez. Coudes près du corps.","Corps vertical = triceps. Corps penché = pectoraux.","Pectoraux, Épaules",73),
    ("Extension poulie haute","Triceps","machine","Coudes fixes près du corps, poussez vers le bas jusqu'à extension complète, tournez les poignets vers l'extérieur.","Coudes collés aux flancs — ils NE bougent PAS.","Chef latéral et médial du triceps",86),
    ("Squat","Jambes","free_weight","Pieds dans la largeur des épaules, pointes légèrement ouvertes. Descendez en poussant les genoux dans l'axe des pieds, dos droit, cuisses parallèles. Remontez fort.","Les genoux suivent la direction des orteils. Inspirez profondément avant de descendre.","Fessiers, Ischio-jambiers, Mollets, Dos",29),
    ("Leg Press","Jambes","machine","Pieds sur la plateforme à largeur d'épaules. Descendez jusqu'à 90°, poussez sans verrouiller les genoux.","Pieds hauts = plus de fessiers/ischios. Pieds bas = plus de quadriceps.","Fessiers, Ischio-jambiers",0),
    ("Leg Extension","Jambes","machine","Tendez les jambes jusqu'à l'horizontale en contractant les quadriceps, descendez lentement.","Pointer les orteils légèrement vers l'extérieur aide à sentir le vaste interne.","Quadriceps uniquement",105),
    ("Leg Curl couché","Jambes","machine","Allongé face vers le bas. Fléchissez les genoux en ramenant les talons vers les fessiers, descendez lentement.","Étirement complet en bas = plus d'hypertrophie.","Ischio-jambiers, Mollets",116),
    ("Romanian Deadlift","Jambes","free_weight","Poussez les hanches vers l'arrière en descendant la barre le long des jambes, dos parfaitement plat. Remontez en poussant les hanches vers l'avant.","Ce n'est PAS un squat : les genoux restent presque droits.","Fessiers, Bas du dos",0),
    ("Fentes","Jambes","free_weight","Grand pas en avant, descendez jusqu'à ce que le genou arrière effleure le sol. Genou avant au-dessus du pied.","Excellent pour corriger les déséquilibres gauche/droite.","Fessiers, Ischio-jambiers",0),
    ("Hip Thrust","Fessiers","free_weight","Dos appuyé sur un banc (omoplates), barre sur les hanches avec pad. Poussez les hanches vers le haut, contractez fort en haut.","L'exercice le plus efficace pour les fessiers. Maintenez 1 seconde en haut.","Ischio-jambiers, Quadriceps",0),
    ("Mollets debout machine","Mollets","machine","Debout sur la plateforme, épaules sous les coussinets. Montez sur la pointe des pieds, contractez, descendez jusqu'à l'étirement maximum.","Amplitude complète est clé. Les mollets répondent bien aux séries longues (15-20 reps).","Soléaire",0),
    ("Mollets assis machine","Mollets","machine","Genoux fléchis à 90°. Montez sur la pointe des pieds, contractez, descendez en étirement complet.","Genou fléchi = soléaire dominant. Genou tendu = gastrocnémien dominant.","Gastrocnémien",0),
    ("Crunch","Abdominaux","bodyweight","Enroulez le haut du tronc vers les genoux en expirant, en contractant les abdos. Descendez lentement.","Mouvement court et contrôlé. Le bas du dos reste au sol.","Abdominaux droits",0),
    ("Planche","Abdominaux","bodyweight","En appui sur les avant-bras et les orteils, corps en ligne droite. Contractez abdominaux, fessiers et quadriceps. Maintenez.","Les hanches ne montent ni ne descendent. Progression : 20s → 30s → 60s → 2min.","Dorsaux, Fessiers, Quadriceps",0),
    ("Relevé de jambes","Abdominaux","bodyweight","Suspendu à une barre ou allongé. Levez les jambes tendues jusqu'à l'horizontale ou plus. Descendez lentement.","En suspension = plus difficile. Jambes tendues = plus intense.","Psoas, Hip-flexors",0),
    ("Russian Twist","Abdominaux","bodyweight","Assis, buste incliné à 45°. Tournez le buste de gauche à droite en amenant les mains d'un côté à l'autre.","Plus les pieds sont levés, plus c'est difficile. Ajouter un poids pour progresser.","Obliques, Bas du dos",0),
    ("Crunch poulie haute","Abdominaux","machine","À genoux face à la poulie haute avec corde. Enroulez le buste vers le bas en contractant les abdos.","Permet de surcharger progressivement les abdominaux comme n'importe quel muscle.","Abdominaux droits, Obliques",0),
    ("Muscle Up","Full Body","calisthenics","Traction explosive jusqu'au-delà de la barre, puis transition en dips. Deux phases : pull puis push.","La transition est la partie la plus difficile. Travailler les 'negative muscle-up'.","Dos, Pectoraux, Triceps, Core",0),
    ("Front Lever","Dos","calisthenics","Suspendu à une barre, corps horizontal face vers le haut, bras tendus.","Progressions : tuck → advanced tuck → one leg → straddle → full.","Biceps, Core, Grand dorsal",0),
    ("Back Lever","Dos","calisthenics","Suspendu à une barre, corps horizontal face vers le bas, bras tendus derrière.","Moins difficile que le front lever mais requiert une bonne mobilité d'épaule.","Pectoraux, Biceps, Core",0),
    ("Planche (figure)","Épaules","calisthenics","En appui sur les deux mains, corps horizontal face vers le bas, bras tendus.","Progression : lean → tuck → advanced tuck → straddle → full. Des années d'entraînement.","Core, Triceps, Grand dorsal",0),
    ("Human Flag","Full Body","calisthenics","Corps horizontal perpendiculaire à un poteau, maintenu par la force des bras.","Une main pousse, l'autre tire. Travailler les lateral press au sol pour progresser.","Obliques, Épaules, Grand dorsal, Core",0),
    ("L-Sit","Abdominaux","calisthenics","En appui sur deux barres, corps soulevé, jambes tendues horizontalement formant un L.","Progressions : genoux fléchis → une jambe → full L-sit → V-sit.","Psoas, Quadriceps, Triceps",0),
    ("Dragon Flag","Abdominaux","calisthenics","Allongé sur un banc, corps monte en appui sur les épaules puis descend lentement, rigide.","Descente excentrique lente = progrès rapides. Corps rigide comme une planche.","Core complet, Psoas, Épaules",0),
    ("Pseudo Planche Push Up","Pectoraux","calisthenics","Position pompes avec doigts pointés vers les pieds. Corps légèrement incliné vers l'avant.","Plus l'inclinaison vers l'avant est grande, plus c'est difficile.","Épaules, Triceps, Core",0),
    ("Archer Pull Up","Dos","calisthenics","Un bras tire, l'autre tendu sur le côté. Transition vers la traction un bras.","Plus le bras assistant est tendu, plus c'est difficile.","Grand dorsal, Biceps, Rhomboïdes",0),
    ("Handstand Push Up","Épaules","calisthenics","En équilibre sur les mains (dos au mur), descendez la tête vers le sol, remontez.","Progressions : wall HSPU → chest to wall → freestanding.","Triceps, Trapèzes",0),
    ("One Arm Pull Up","Dos","calisthenics","Traction stricte avec un seul bras. L'autre bras reste le long du corps.","Progressions : assisted OAP → archer pull-up → negative OAP → full OAP.","Grand dorsal, Biceps, Core",0),
    ("Explosive Pull Up","Dos","calisthenics","Traction explosive pour amener le buste bien au-dessus de la barre.","Base du muscle-up. Progressions : poitrine à la barre → lâcher → muscle-up.","Grand dorsal, Biceps, Trapèzes",0),
    ("Tractions lestées","Dos","calisthenics","Tractions classiques avec poids supplémentaire (ceinture lestée, gilet).","Une fois 15+ tractions strictes, ajouter du poids pour continuer à progresser.","Biceps, Rhomboïdes, Grand rond",0),
    ("Dips lestés","Triceps","calisthenics","Dips aux barres parallèles avec poids supplémentaire.","Ajouter du poids progressivement une fois les dips classiques faciles.","Pectoraux, Épaules antérieures",0),
]

PROGRAMS_SEED = [
    {"name":"Full Body 3j/semaine","description":"Programme complet corps entier, idéal pour les débutants et intermédiaires","sessions_per_week":3,"sessions":[
        ("Séance A","Lundi",[("Squat",4,"8-10"),("Développé couché",4,"8-10"),("Rowing barre",4,"8-10"),("Développé militaire",3,"10-12"),("Curl barre",3,"12"),("Extension poulie haute",3,"12")]),
        ("Séance B","Mercredi",[("Romanian Deadlift",4,"10"),("Développé incliné haltères",4,"10-12"),("Lat Pulldown",4,"10-12"),("Élévations latérales",4,"15"),("Curl haltères",3,"12"),("Skull Crusher",3,"10")]),
        ("Séance C","Vendredi",[("Leg Press",4,"12-15"),("Chest Press Machine",4,"10-12"),("Rowing assis machine",3,"12"),("Face Pull",4,"15-20"),("Hip Thrust",3,"12-15"),("Planche",3,"60s")]),
    ]},
    {"name":"PPL 6j/semaine","description":"Push Pull Legs — volume élevé pour intermédiaires et avancés","sessions_per_week":6,"sessions":[
        ("Push A","Lundi",[("Développé couché",4,"6-8"),("Développé incliné haltères",3,"10-12"),("Écarté haltères",3,"12-15"),("Développé militaire",3,"8-10"),("Élévations latérales",4,"12-15"),("Skull Crusher",3,"10-12")]),
        ("Pull A","Mardi",[("Soulevé de terre",4,"5-6"),("Tractions",4,"Max"),("Rowing barre",3,"8-10"),("Lat Pulldown",3,"10-12"),("Curl barre",3,"10-12"),("Curl marteau",3,"12-15")]),
        ("Legs A","Mercredi",[("Squat",5,"5-8"),("Leg Press",3,"12-15"),("Romanian Deadlift",3,"10"),("Leg Curl couché",3,"12"),("Mollets debout machine",5,"15")]),
        ("Push B","Jeudi",[("Chest Press Machine",4,"8-10"),("Dips",4,"10-12"),("Cable Crossover",3,"15"),("Arnold Press",3,"10-12"),("Élévations frontales",3,"12-15"),("Extension au-dessus tête",3,"12")]),
        ("Pull B","Vendredi",[("Rowing haltère",4,"10-12"),("Face Pull",4,"15-20"),("Rowing assis machine",3,"12"),("Curl poulie basse",3,"12-15"),("Curl haltères",3,"12")]),
        ("Legs B","Samedi",[("Fentes",4,"12"),("Hip Thrust",4,"12-15"),("Leg Extension",3,"15"),("Leg Curl couché",3,"15"),("Mollets assis machine",5,"20")]),
    ]},
    {"name":"Calisthenics Débutant","description":"Street workout — construire les bases pour les figures avancées","sessions_per_week":3,"sessions":[
        ("Fondamentaux Push","Lundi",[("Pompes",4,"Max"),("Dips",4,"Max"),("Pseudo Planche Push Up",3,"8-10"),("Planche",3,"30-60s")]),
        ("Fondamentaux Pull","Mercredi",[("Tractions",5,"Max"),("Archer Pull Up",3,"6-8"),("L-Sit",4,"20-30s"),("Relevé de jambes",4,"15")]),
        ("Figures & Force","Vendredi",[("Muscle Up",4,"Max"),("Dragon Flag",3,"8-10"),("Squat",4,"20"),("Fentes",3,"15")]),
    ]},
    {"name":"Upper / Lower 4j/semaine","description":"Haut / Bas du corps, 4 séances, force + hypertrophie","sessions_per_week":4,"sessions":[
        ("Upper A — Force","Lundi",[("Développé couché",4,"5-6"),("Tractions",4,"6-8"),("Développé militaire",3,"6-8"),("Rowing barre",3,"6-8"),("Dips lestés",3,"8-10")]),
        ("Lower A — Force","Mardi",[("Squat",5,"5"),("Romanian Deadlift",3,"8"),("Leg Press",3,"10"),("Leg Curl couché",3,"10"),("Mollets debout machine",4,"12")]),
        ("Upper B — Hypertrophie","Jeudi",[("Développé incliné haltères",4,"10-12"),("Lat Pulldown",4,"10-12"),("Écarté haltères",3,"12-15"),("Rowing haltère",3,"12"),("Curl barre",3,"12"),("Extension poulie haute",3,"12")]),
        ("Lower B — Hypertrophie","Vendredi",[("Leg Press",4,"12-15"),("Fentes",3,"12"),("Leg Extension",3,"15"),("Hip Thrust",3,"12-15"),("Mollets assis machine",4,"20")]),
    ]},
]


# ── INIT SEED ──────────────────────────────────────────────────────────────

def init_seed():
    """Seed exercises and programs if tables are empty. Safe to call multiple times."""
    client = sb()
    res = client.table("exercises").select("id", count="exact").limit(1).execute()
    if getattr(res, 'count', 0) and res.count > 0:
        return

    exercises = [
        {"id": new_id(), "name": n, "muscle_group": mg, "category": cat,
         "description": desc, "tips": tips, "muscles_secondary": sec,
         "wger_id": wger_id, "is_custom": False}
        for n, mg, cat, desc, tips, sec, wger_id in EXERCISES_SEED
    ]
    # Insert in batches of 20 to avoid payload limits
    for i in range(0, len(exercises), 20):
        client.table("exercises").insert(exercises[i:i+20]).execute()

    ex_map = {e["name"]: e["id"] for e in exercises}

    for p_data in PROGRAMS_SEED:
        prog_id = new_id()
        client.table("programs").insert({
            "id": prog_id, "name": p_data["name"],
            "description": p_data["description"],
            "sessions_per_week": p_data["sessions_per_week"],
            "is_custom": False, "created_at": str(date.today())
        }).execute()
        for s_name, s_day, s_exs in p_data["sessions"]:
            sess_id = new_id()
            client.table("sessions").insert({
                "id": sess_id, "program_id": prog_id,
                "name": s_name, "day_of_week": s_day
            }).execute()
            se_rows = [{"id": new_id(), "session_id": sess_id,
                        "exercise_id": ex_map[en], "sets": sets, "target_reps": reps}
                       for en, sets, reps in s_exs if en in ex_map]
            if se_rows:
                client.table("session_exercises").insert(se_rows).execute()


# ── STATIC ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── EXERCISES ──────────────────────────────────────────────────────────────

@app.route("/api/exercises", methods=["GET"])
def get_exercises():
    q = sb().table("exercises").select("*").order("name")
    cat = request.args.get("category")
    if cat:
        q = q.eq("category", cat)
    return jsonify(q.execute().data)

@app.route("/api/exercises", methods=["POST"])
def create_exercise():
    d = request.json
    ex = {"id": new_id(), "name": d["name"], "muscle_group": d.get("muscle_group",""),
          "category": d.get("category","free_weight"), "description": d.get("description",""),
          "tips": "", "muscles_secondary": "", "wger_id": 0, "is_custom": True}
    sb().table("exercises").insert(ex).execute()
    return jsonify(ex)

@app.route("/api/exercises/<ex_id>", methods=["DELETE"])
def delete_exercise(ex_id):
    sb().table("exercises").delete().eq("id", ex_id).execute()
    return jsonify({"ok": True})


# ── PROGRAMS ───────────────────────────────────────────────────────────────

def _build_programs_response():
    programs  = sb().table("programs").select("*").order("name").execute().data
    sessions  = sb().table("sessions").select("*").execute().data
    sess_exs  = sb().table("session_exercises").select("*").execute().data
    exercises = sb().table("exercises").select("*").execute().data
    ex_map = {e["id"]: e for e in exercises}

    sess_by_prog = defaultdict(list)
    for s in sessions:
        sess_by_prog[s["program_id"]].append(s)

    se_by_sess = defaultdict(list)
    for se in sess_exs:
        ex = ex_map.get(se["exercise_id"], {})
        se["exercise_name"] = ex.get("name","?")
        se["muscle_group"]  = ex.get("muscle_group","")
        se["category"]      = ex.get("category","")
        se_by_sess[se["session_id"]].append(se)

    for p in programs:
        p["sessions"] = sess_by_prog.get(p["id"], [])
        for s in p["sessions"]:
            s["exercises"] = se_by_sess.get(s["id"], [])
    return programs

@app.route("/api/programs", methods=["GET"])
def get_programs():
    return jsonify(_build_programs_response())

@app.route("/api/programs", methods=["POST"])
def create_program():
    d = request.json
    prog = {"id": new_id(), "name": d["name"], "description": d.get("description",""),
            "sessions_per_week": d.get("sessions_per_week",3),
            "is_custom": True, "created_at": str(date.today())}
    sb().table("programs").insert(prog).execute()
    prog["sessions"] = []
    return jsonify(prog)

@app.route("/api/programs/<pid>", methods=["DELETE"])
def delete_program(pid):
    sb().table("programs").delete().eq("id", pid).execute()
    return jsonify({"ok": True})

@app.route("/api/programs/<pid>/sessions", methods=["POST"])
def add_session(pid):
    d = request.json
    session = {"id": new_id(), "program_id": pid,
               "name": d["name"], "day_of_week": d.get("day_of_week","")}
    sb().table("sessions").insert(session).execute()
    session["exercises"] = []
    return jsonify(session)

@app.route("/api/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    sb().table("sessions").delete().eq("id", sid).execute()
    return jsonify({"ok": True})

@app.route("/api/sessions/<sid>/exercises", methods=["POST"])
def add_session_exercise(sid):
    d = request.json
    se = {"id": new_id(), "session_id": sid, "exercise_id": d["exercise_id"],
          "sets": d.get("sets",3), "target_reps": d.get("target_reps","8-12")}
    sb().table("session_exercises").insert(se).execute()
    return jsonify(se)

@app.route("/api/session_exercises/<se_id>", methods=["DELETE"])
def delete_session_exercise(se_id):
    sb().table("session_exercises").delete().eq("id", se_id).execute()
    return jsonify({"ok": True})


# ── LOGS ───────────────────────────────────────────────────────────────────

def _enrich_logs(logs):
    exercises = sb().table("exercises").select("id,name,category,muscle_group").execute().data
    programs  = sb().table("programs").select("id,name").execute().data
    sessions  = sb().table("sessions").select("id,name").execute().data
    ex_map   = {e["id"]: e for e in exercises}
    prog_map = {p["id"]: p["name"] for p in programs}
    sess_map = {s["id"]: s["name"] for s in sessions}
    for log in logs:
        log["program_name"] = prog_map.get(log.get("program_id"),"")
        log["session_name"] = sess_map.get(log.get("session_id"),"Séance libre")
        for s in (log.get("sets") or []):
            ex = ex_map.get(s.get("exercise_id"),{})
            s["exercise_name"] = ex.get("name","?")
            s["category"]      = ex.get("category","")
    return logs

@app.route("/api/logs", methods=["GET"])
def get_logs():
    limit = int(request.args.get("limit", 200))
    logs = sb().table("logs").select("*").order("log_date", desc=True).limit(limit).execute().data
    return jsonify(_enrich_logs(logs))

@app.route("/api/logs", methods=["POST"])
def create_log():
    d = request.json
    log = {"id": new_id(), "session_id": d.get("session_id"), "program_id": d.get("program_id"),
           "log_date": d.get("log_date", str(date.today())), "notes": d.get("notes",""),
           "created_at": datetime.now().isoformat(), "sets": d.get("sets",[])}
    sb().table("logs").insert(log).execute()
    return jsonify(log)

@app.route("/api/logs/<lid>", methods=["DELETE"])
def delete_log(lid):
    sb().table("logs").delete().eq("id", lid).execute()
    return jsonify({"ok": True})


# ── STATS ──────────────────────────────────────────────────────────────────

@app.route("/api/stats/summary")
def stats_summary():
    logs = sb().table("logs").select("log_date,sets").execute().data
    today = date.today()
    this_month = today.strftime("%Y-%m")
    this_week  = get_week_key(str(today))
    month_s = sum(1 for l in logs if l["log_date"][:7] == this_month)
    week_s  = sum(1 for l in logs if get_week_key(l["log_date"]) == this_week)
    vol = sum((s.get("weight") or 0)*(s.get("reps") or 0) for l in logs for s in (l.get("sets") or []))
    prs = {}
    for l in logs:
        for s in (l.get("sets") or []):
            ex_id = s.get("exercise_id"); w = s.get("weight") or 0
            if w > 0 and (ex_id not in prs or w > prs[ex_id]): prs[ex_id] = w
    return jsonify({"month_sessions": month_s, "week_sessions": week_s,
                    "total_volume": round(vol), "pr_count": len(prs), "total_sessions": len(logs)})

@app.route("/api/stats/personal_records")
def get_prs():
    logs = sb().table("logs").select("log_date,sets").execute().data
    exs  = sb().table("exercises").select("*").execute().data
    ex_map = {e["id"]: e for e in exs}
    prs = {}
    for l in logs:
        for s in (l.get("sets") or []):
            ex_id = s.get("exercise_id"); w = s.get("weight") or 0
            if w > 0 and (ex_id not in prs or w > prs[ex_id]["max_weight"]):
                ex = ex_map.get(ex_id,{})
                prs[ex_id] = {"exercise_id": ex_id, "exercise_name": ex.get("name","?"),
                              "category": ex.get("category",""), "muscle_group": ex.get("muscle_group",""),
                              "max_weight": w, "reps_at_max": s.get("reps"), "last_performed": l["log_date"][:10]}
    return jsonify(sorted(prs.values(), key=lambda x: x["exercise_name"]))


# ── PLOTLY CHARTS ──────────────────────────────────────────────────────────

@app.route("/api/charts/weekly_volume")
def chart_weekly_volume():
    logs = sb().table("logs").select("log_date,sets").execute().data
    week_vol = defaultdict(float); week_sess = defaultdict(int)
    for l in logs:
        wk = get_week_key(l["log_date"]); week_sess[wk] += 1
        for s in (l.get("sets") or []): week_vol[wk] += (s.get("weight") or 0)*(s.get("reps") or 0)
    weeks  = sorted(set(list(week_vol.keys())+list(week_sess.keys())))[-16:]
    labels = [f"S{w.split('-W')[1]} '{w[:4][2:]}" for w in weeks]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=labels, y=[round(week_vol[w]) for w in weeks], name="Volume (kg)",
        marker=dict(color="#e94560", opacity=0.85, line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>Volume : <b>%{y} kg</b><extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=labels, y=[week_sess[w] for w in weeks], name="Séances",
        mode="lines+markers", line=dict(color="#00d4ff", width=2.5),
        marker=dict(color="#00d4ff", size=7, line=dict(color="#111118", width=1.5)),
        hovertemplate="<b>%{x}</b><br>Séances : <b>%{y}</b><extra></extra>"), secondary_y=True)
    fig.update_layout(title=dict(text="Volume & Séances Hebdomadaires", font=dict(color="#f0f0f8", size=14)),
                      **{k:v for k,v in LAYOUT_BASE.items() if k!="colorway"})
    fig.update_yaxes(title_text="Volume (kg)", secondary_y=False, **AXIS_STYLE)
    fig.update_yaxes(title_text="Séances", secondary_y=True, tickfont=dict(color="#00d4ff"),
                     gridcolor="#1e1e2a", linecolor="#2a2a38")
    fig.update_xaxes(**AXIS_STYLE)
    return jsonify(json.loads(fig.to_json()))

@app.route("/api/charts/muscle_distribution")
def chart_muscle_dist():
    logs = sb().table("logs").select("sets").execute().data
    exs  = sb().table("exercises").select("id,muscle_group").execute().data
    ex_map = {e["id"]: e for e in exs}
    muscle_vol = defaultdict(float)
    for l in logs:
        for s in (l.get("sets") or []):
            ex = ex_map.get(s.get("exercise_id"),{})
            muscle_vol[ex.get("muscle_group","Autre")] += (s.get("weight") or 0)*(s.get("reps") or 0)
    if not muscle_vol: return jsonify({})
    items = sorted(muscle_vol.items(), key=lambda x: x[1], reverse=True)[:8]
    fig = go.Figure(go.Pie(labels=[i[0] for i in items], values=[round(i[1]) for i in items],
        hole=0.58, textinfo="label+percent", textfont=dict(size=11, color="#d0d0e8"),
        marker=dict(colors=["#e94560","#00d4ff","#ffd740","#00e676","#c792ea","#ff6b6b","#82aaff","#ffab40"],
                    line=dict(color="#111118", width=2)),
        hovertemplate="<b>%{label}</b><br>%{value} kg<br>%{percent}<extra></extra>"))
    fig.update_layout(title=dict(text="Répartition du Volume par Muscle", font=dict(color="#f0f0f8", size=14)),
                      **LAYOUT_BASE)
    return jsonify(json.loads(fig.to_json()))

@app.route("/api/charts/exercise_progress/<ex_id>")
def chart_exercise_progress(ex_id):
    logs = sb().table("logs").select("log_date,sets").execute().data
    exs  = sb().table("exercises").select("*").execute().data
    ex_map = {e["id"]: e for e in exs}
    ex = ex_map.get(ex_id)
    if not ex: abort(404)
    is_cali = ex.get("category") == "calisthenics"
    date_data = defaultdict(lambda: {"max_weight":0,"max_reps":0,"volume":0})
    for l in logs:
        for s in (l.get("sets") or []):
            if s.get("exercise_id") != ex_id: continue
            d = l["log_date"][:10]; w = s.get("weight") or 0; r = s.get("reps") or 0
            date_data[d]["max_weight"] = max(date_data[d]["max_weight"], w)
            date_data[d]["max_reps"]   = max(date_data[d]["max_reps"], r)
            date_data[d]["volume"]    += w*r
    if not date_data: return jsonify({})
    dates = sorted(date_data.keys())
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
        subplot_titles=["Poids Max (kg)" if not is_cali else "Reps Max","Volume Total (kg)"],
        vertical_spacing=0.14, row_heights=[0.6,0.4])
    y_top = [date_data[d]["max_weight"] for d in dates] if not is_cali else [date_data[d]["max_reps"] for d in dates]
    c = "#e94560" if not is_cali else "#00e676"
    rgb = {"#e94560":"233,69,96","#00e676":"0,230,118"}[c]
    fig.add_trace(go.Scatter(x=dates, y=y_top, mode="lines+markers",
        name="Poids Max" if not is_cali else "Reps Max",
        line=dict(color=c, width=2.5), marker=dict(color=c, size=7, line=dict(color="#111118",width=1.5)),
        fill="tozeroy", fillcolor=f"rgba({rgb},0.1)",
        hovertemplate="%{x}<br><b>%{y:.1f}"+(" kg" if not is_cali else " reps")+"</b><extra></extra>"), row=1, col=1)
    fig.add_trace(go.Bar(x=dates, y=[round(date_data[d]["volume"]) for d in dates], name="Volume",
        marker=dict(color="#00d4ff",opacity=0.75,line=dict(width=0)),
        hovertemplate="%{x}<br>Volume : <b>%{y} kg</b><extra></extra>"), row=2, col=1)
    fig.update_layout(title=dict(text=f"Progression — {ex.get('name','')}",font=dict(color="#f0f0f8",size=14)),
                      showlegend=True, **LAYOUT_BASE)
    for ax in ["xaxis","xaxis2","yaxis","yaxis2"]: fig.update_layout(**{ax: AXIS_STYLE})
    return jsonify(json.loads(fig.to_json()))

@app.route("/api/charts/heatmap")
def chart_heatmap():
    logs = sb().table("logs").select("log_date,sets").execute().data
    exs  = sb().table("exercises").select("id,muscle_group").execute().data
    ex_map = {e["id"]: e for e in exs}
    data = defaultdict(lambda: defaultdict(float))
    for l in logs:
        wk = get_week_key(l["log_date"])
        for s in (l.get("sets") or []):
            ex = ex_map.get(s.get("exercise_id"),{})
            data[wk][ex.get("muscle_group","Autre")] += (s.get("weight") or 0)*(s.get("reps") or 0)
    if not data: return jsonify({})
    weeks = sorted(data.keys())[-14:]; muscles = sorted({mg for wk in weeks for mg in data[wk].keys()})
    fig = go.Figure(go.Heatmap(z=[[round(data[wk].get(mg,0)) for wk in weeks] for mg in muscles],
        x=[f"S{w.split('-W')[1]}" for w in weeks], y=muscles,
        colorscale=[[0,"#0a0a18"],[0.15,"#1a1a3e"],[0.5,"#e94560"],[1,"#ffd740"]],
        hovertemplate="Sem. %{x} — %{y}<br><b>%{z} kg</b><extra></extra>",
        colorbar=dict(tickfont=dict(color="#8888aa",size=10),title=dict(text="kg",font=dict(color="#8888aa")))))
    fig.update_layout(title=dict(text="Heatmap Volume — Muscle × Semaine",font=dict(color="#f0f0f8",size=14)),
                      **LAYOUT_BASE)
    return jsonify(json.loads(fig.to_json()))

@app.route("/api/charts/pr_bars")
def chart_pr_bars():
    logs = sb().table("logs").select("log_date,sets").execute().data
    exs  = sb().table("exercises").select("*").execute().data
    ex_map = {e["id"]: e for e in exs}
    prs = {}
    for l in logs:
        for s in (l.get("sets") or []):
            ex_id = s.get("exercise_id"); w = s.get("weight") or 0
            if w > 0 and (ex_id not in prs or w > prs[ex_id]["weight"]):
                ex = ex_map.get(ex_id,{})
                prs[ex_id] = {"name":ex.get("name","?"),"weight":w,"reps":s.get("reps",0),
                               "muscle":ex.get("muscle_group","Autre"),"date":l["log_date"][:10]}
    if not prs: return jsonify({})
    items = sorted(prs.values(), key=lambda x: x["weight"], reverse=True)[:15]
    MCOL = {"Pectoraux":"#e94560","Dos":"#00d4ff","Jambes":"#00e676","Épaules":"#ffd740",
             "Biceps":"#c792ea","Triceps":"#ff6b6b","Fessiers":"#82aaff","Mollets":"#ffab40",
             "Abdominaux":"#80cbc4","Full Body":"#ff80ab"}
    fig = go.Figure(go.Bar(y=[i["name"] for i in items], x=[i["weight"] for i in items], orientation="h",
        marker=dict(color=[MCOL.get(i["muscle"],"#8888aa") for i in items],line=dict(width=0),opacity=0.9),
        text=[f"  {i['weight']} kg" for i in items], textposition="outside",
        textfont=dict(color="#c0c0d0",size=11),
        customdata=[f"<b>{i['name']}</b><br>{i['weight']} kg × {i['reps']} reps<br>{i['date']}" for i in items],
        hovertemplate="%{customdata}<extra></extra>"))
    fig.update_layout(title=dict(text="Top 15 Records Personnels",font=dict(color="#f0f0f8",size=14)),
                      height=max(360,len(items)*30+90), xaxis_title="Poids Max (kg)", **LAYOUT_BASE)
    fig.update_xaxes(**AXIS_STYLE); fig.update_yaxes(**AXIS_STYLE)
    return jsonify(json.loads(fig.to_json()))


# ── EXCEL EXPORT ───────────────────────────────────────────────────────────

def _build_excel_bytes():
    logs  = sb().table("logs").select("*").order("log_date", desc=True).execute().data
    exs   = sb().table("exercises").select("*").execute().data
    progs = sb().table("programs").select("*").execute().data
    sess  = sb().table("sessions").select("*").execute().data
    ex_map   = {e["id"]: e for e in exs}
    prog_map = {p["id"]: p["name"] for p in progs}
    sess_map = {s["id"]: s["name"] for s in sess}

    wb  = openpyxl.Workbook()
    BG  = PatternFill("solid",fgColor="0a0a0f"); BG2 = PatternFill("solid",fgColor="16161f")
    BG3 = PatternFill("solid",fgColor="1e1e2a"); RED  = PatternFill("solid",fgColor="e94560")
    GOLD = PatternFill("solid",fgColor="b8860b"); TEAL = PatternFill("solid",fgColor="006064")
    thin = Border(left=Side(style="thin",color="2a2a38"),right=Side(style="thin",color="2a2a38"),
                  top=Side(style="thin",color="2a2a38"),bottom=Side(style="thin",color="2a2a38"))
    ctr = Alignment(horizontal="center",vertical="center")

    def cs(ws,r,c,fill,font):
        cell=ws.cell(row=r,column=c); cell.fill=fill; cell.font=font; cell.border=thin; cell.alignment=ctr
        return cell

    ws = wb.active; ws.title = "📋 Historique"; ws.sheet_view.showGridLines = False
    ws['A1'] = "🏋️  FITTRACKER — HISTORIQUE"
    ws['A1'].font=Font(name="Calibri",bold=True,color="FFFFFF",size=14); ws['A1'].fill=RED
    ws['A1'].alignment=ctr; ws.merge_cells("A1:I1"); ws.row_dimensions[1].height=30
    for i,h in enumerate(["Date","Programme","Séance","Exercice","Catégorie","Set","Reps","Poids (kg)","Volume (kg)"],1):
        cs(ws,2,i,BG,Font(name="Calibri",bold=True,color="e94560",size=11)).value=h
    row_n=3
    for log in logs:
        for s in (log.get("sets") or []):
            ex=ex_map.get(s.get("exercise_id"),{}); w=s.get("weight") or 0; r2=s.get("reps") or 0
            vals=[log["log_date"][:10],prog_map.get(log.get("program_id"),"—"),
                  sess_map.get(log.get("session_id"),"—"),ex.get("name","?"),ex.get("category",""),
                  s.get("set_number",""),s.get("figure") or r2,w or "",round(w*r2,1) if w and r2 else ""]
            fill=BG3 if row_n%2==0 else BG2
            for j,v in enumerate(vals,1): cs(ws,row_n,j,fill,Font(name="Calibri",color="e0e0f0",size=10)).value=v
            row_n+=1
    for col,w in zip("ABCDEFGHI",[14,24,24,28,14,6,8,12,12]): ws.column_dimensions[col].width=w

    ws2=wb.create_sheet("🏆 Records"); ws2.sheet_view.showGridLines=False
    ws2['A1']="🏆  PERSONAL RECORDS"; ws2['A1'].font=Font(name="Calibri",bold=True,color="FFFFFF",size=14)
    ws2['A1'].fill=GOLD; ws2['A1'].alignment=ctr; ws2.merge_cells("A1:F1"); ws2.row_dimensions[1].height=30
    for i,h in enumerate(["Exercice","Catégorie","Muscle","Poids Max (kg)","Reps","Dernière perf"],1):
        cs(ws2,2,i,BG,Font(name="Calibri",bold=True,color="ffd740",size=11)).value=h
    prs={}
    for l in logs:
        for s in (l.get("sets") or []):
            ex_id=s.get("exercise_id"); w=s.get("weight") or 0
            if w>0 and (ex_id not in prs or w>prs[ex_id]["max_weight"]):
                ex=ex_map.get(ex_id,{})
                prs[ex_id]={"name":ex.get("name","?"),"cat":ex.get("category",""),"mg":ex.get("muscle_group",""),
                             "max_weight":w,"reps":s.get("reps"),"date":l["log_date"][:10]}
    for i,pr in enumerate(sorted(prs.values(),key=lambda x:x["name"]),3):
        fill=BG3 if i%2==0 else BG2
        for j,v in enumerate([pr["name"],pr["cat"],pr["mg"],pr["max_weight"],pr["reps"],pr["date"]],1):
            cs(ws2,i,j,fill,Font(name="Calibri",color="e0e0f0",size=10)).value=v
    for col,w in zip("ABCDEF",[28,14,20,16,8,14]): ws2.column_dimensions[col].width=w

    ws3=wb.create_sheet("📊 Semaines"); ws3.sheet_view.showGridLines=False
    ws3['A1']="📊  RÉSUMÉ HEBDOMADAIRE"; ws3['A1'].font=Font(name="Calibri",bold=True,color="FFFFFF",size=14)
    ws3['A1'].fill=TEAL; ws3['A1'].alignment=ctr; ws3.merge_cells("A1:D1"); ws3.row_dimensions[1].height=30
    for i,h in enumerate(["Semaine","Séances","Volume (kg)","Jours"],1):
        cs(ws3,2,i,BG,Font(name="Calibri",bold=True,color="00d4ff",size=11)).value=h
    week_data=defaultdict(lambda:{"sessions":0,"volume":0.0,"days":set()})
    for l in logs:
        wk=get_week_key(l["log_date"]); week_data[wk]["sessions"]+=1; week_data[wk]["days"].add(l["log_date"][:10])
        for s in (l.get("sets") or []): week_data[wk]["volume"]+=(s.get("weight") or 0)*(s.get("reps") or 0)
    for i,wk in enumerate(sorted(week_data.keys(),reverse=True),3):
        d=week_data[wk]; fill=BG3 if i%2==0 else BG2
        for j,v in enumerate([wk,d["sessions"],round(d["volume"]),len(d["days"])],1):
            cs(ws3,i,j,fill,Font(name="Calibri",color="e0e0f0",size=10)).value=v
    for col,w in zip("ABCD",[14,10,16,10]): ws3.column_dimensions[col].width=w

    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf

@app.route("/api/export/excel")
def export_excel():
    buf = _build_excel_bytes()
    return send_file(buf, as_attachment=True, download_name="fittracker_export.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── SEED ENDPOINT ──────────────────────────────────────────────────────────

@app.route("/api/admin/seed", methods=["POST"])
def admin_seed():
    """POST /api/admin/seed — insère les données si la base est vide."""
    init_seed()
    return jsonify({"ok": True, "message": "Seed effectué."})


# ── ENTRY POINT ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n✅  FitTracker (Supabase) démarré → http://localhost:5000\n")
    app.run(debug=True, port=5000, use_reloader=False)