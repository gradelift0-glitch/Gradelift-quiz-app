import random
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gradelift Quiz", page_icon="🦴", layout="centered")

LOCAL_FILE = "question_bank.xlsx"
LETTERS = ["A", "B", "C", "D"]
REQUIRED = ["ID", "Question", "Image URL", "Option A", "Option B", "Option C",
            "Option D", "Correct", "Explanation", "Structure", "Sub-part"]


def secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


# ---------- Data ----------
@st.cache_data(ttl=300, show_spinner="Loading questions...")
def load_questions(sheet_url: str) -> pd.DataFrame:
    if sheet_url:
        m = re.search(r"/d/([a-zA-Z0-9_-]+)", sheet_url)
        if m:
            csv_url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv"
            g = re.search(r"gid=(\d+)", sheet_url)
            if g:
                csv_url += f"&gid={g.group(1)}"
        else:
            csv_url = sheet_url
        df = pd.read_csv(csv_url)
    else:
        df = pd.read_excel(LOCAL_FILE, sheet_name="Questions")

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in the question bank: {', '.join(missing)}")

    for c in df.columns:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["Correct"] = df["Correct"].str.upper()
    df = df[(df["Question"] != "") & (df["Correct"].isin(LETTERS))]
    df = df[df.apply(lambda r: r[f"Option {r['Correct']}"] != "", axis=1)]
    return df.reset_index(drop=True)


def build_quiz(df: pd.DataFrame, n: int, bone: str):
    """Pick n questions, balanced across bones, with shuffled options."""
    pool = df if bone == "All bones" else df[df["Structure"] == bone]
    groups = {}
    for _, row in pool.iterrows():
        groups.setdefault(row["Structure"], []).append(row)
    for g in groups.values():
        random.shuffle(g)
    picked = []
    while len(picked) < n and any(groups.values()):
        for key in list(groups):
            if groups[key] and len(picked) < n:
                picked.append(groups[key].pop())
    random.shuffle(picked)

    quiz = []
    for row in picked:
        opts = [row[f"Option {l}"] for l in LETTERS if row[f"Option {l}"]]
        correct_text = row[f"Option {row['Correct']}"]
        random.shuffle(opts)
        quiz.append({
            "id": row["ID"], "q": row["Question"], "img": row["Image URL"],
            "options": opts, "correct": correct_text,
            "explanation": row["Explanation"], "bone": row["Structure"],
            "sub": row["Sub-part"], "chosen": None,
        })
    return quiz


# ---------- State ----------
def init_state():
    defaults = {"stage": "login", "name": "", "quiz": [], "idx": 0, "submitted": False}
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def restart():
    st.session_state.update({"stage": "setup", "quiz": [], "idx": 0, "submitted": False})


# ---------- Pages ----------
def page_login():
    st.title("🦴 Gradelift Anatomy Quiz")
    st.write("Upper limb bones. Test yourself and find out what to revise.")
    code_needed = secret("ACCESS_CODE")
    name = st.text_input("Your first name")
    code = st.text_input("Access code", type="password") if code_needed else ""
    if st.button("Start", type="primary"):
        if code_needed and code.strip().lower() != str(code_needed).strip().lower():
            st.error("That access code is not correct.")
            return
        st.session_state.name = name.strip()
        st.session_state.stage = "setup"
        st.rerun()


def page_setup(df):
    st.title("Set up your quiz")
    bones = sorted(df["Structure"].unique())
    bone = st.selectbox("Which bone(s)?", ["All bones"] + bones)
    available = len(df) if bone == "All bones" else int((df["Structure"] == bone).sum())
    options = sorted({n for n in (10, 15, 20, available) if n <= available})
    n = st.selectbox("How many questions?", options, index=min(1, len(options) - 1))
    if st.button("Begin quiz", type="primary"):
        st.session_state.quiz = build_quiz(df, n, bone)
        st.session_state.idx = 0
        st.session_state.submitted = False
        st.session_state.stage = "quiz"
        st.rerun()


def page_quiz():
    quiz = st.session_state.quiz
    idx = st.session_state.idx
    q = quiz[idx]
    st.progress(idx / len(quiz))
    st.caption(f"Question {idx + 1} of {len(quiz)}")
    if q["img"]:
        st.image(q["img"], width="stretch")
    st.markdown(f"**{q['q']}**")

    if not st.session_state.submitted:
        choice = st.radio("Choose one", q["options"], index=None,
                          key=f"choice_{idx}", label_visibility="collapsed")
        if st.button("Submit answer", type="primary", disabled=choice is None):
            q["chosen"] = choice
            st.session_state.submitted = True
            st.rerun()
    else:
        if q["chosen"] == q["correct"]:
            st.success(f"Correct: {q['correct']}")
        else:
            st.error(f"Not quite. You chose: {q['chosen']}")
            st.info(f"Correct answer: {q['correct']}")
        if q["explanation"]:
            st.write(q["explanation"])
        last = idx == len(quiz) - 1
        if st.button("See my results" if last else "Next question", type="primary"):
            st.session_state.submitted = False
            if last:
                st.session_state.stage = "result"
            else:
                st.session_state.idx += 1
            st.rerun()


def status_of(pct):
    if pct >= 75:
        return "🟢", "strong"
    if pct >= 50:
        return "🟡", "revise"
    return "🔴", "weak"


def page_result():
    quiz = st.session_state.quiz
    name = st.session_state.name
    total = len(quiz)
    correct = sum(1 for q in quiz if q["chosen"] == q["correct"])
    st.title("Your results")
    st.subheader(f"{name + ', you' if name else 'You'} scored {correct}/{total} ({round(100 * correct / total)}%)")

    # Per bone
    bones = {}
    for q in quiz:
        b = bones.setdefault(q["bone"], {"right": 0, "total": 0, "subs": {}})
        b["total"] += 1
        right = q["chosen"] == q["correct"]
        b["right"] += int(right)
        s = b["subs"].setdefault(q["sub"], [0, 0])
        s[0] += int(right)
        s[1] += 1

    scored = []
    for bone, b in bones.items():
        if b["total"] >= 2:
            scored.append((bone, b, 100 * b["right"] / b["total"]))
    scored.sort(key=lambda x: x[2])

    st.markdown("### Score by bone")
    for bone, b, pct in scored:
        icon, _ = status_of(pct)
        st.write(f"{icon} **{bone}**: {b['right']}/{b['total']} ({round(pct)}%)")
    for bone, b in bones.items():
        if b["total"] < 2:
            st.caption(f"{bone}: only {b['total']} question, too few to judge.")

    strong = [bone for bone, _, p in scored if p >= 75]
    needs = [(bone, b, p) for bone, b, p in scored if p < 75]

    st.markdown("### What to do next")
    if strong:
        st.write("✅ You are strong in: **" + ", ".join(strong) + "**.")
    if not needs:
        st.write("Great work. Try a longer quiz to test yourself further.")
    for bone, b, p in needs:
        icon, label = status_of(p)
        if label == "weak":
            line = f"{icon} Go and review the **{bone}** again. You got {b['right']} of {b['total']} right."
        else:
            line = f"{icon} Revise the **{bone}** a bit more. You got {b['right']} of {b['total']} right."
        weak_subs = [sp for sp, (r, t) in b["subs"].items() if t >= 2 and r / t < 0.6 and sp]
        if weak_subs:
            line += " Focus especially on: " + ", ".join(weak_subs) + "."
        st.write(line)

    missed = [q for q in quiz if q["chosen"] != q["correct"]]
    if missed:
        with st.expander(f"See the {len(missed)} question(s) you missed"):
            for q in missed:
                if q["img"]:
                    st.image(q["img"], width="stretch")
                st.markdown(f"**{q['q']}**")
                st.write(f"You chose: {q['chosen']}")
                st.write(f"Correct: {q['correct']}")
                if q["explanation"]:
                    st.caption(q["explanation"])
                st.divider()

    st.caption("Spotted a mistake or something confusing? Tell us in the class group.")

    st.divider()
    if st.button("Take another quiz"):
        restart()
        st.rerun()


# ---------- Main ----------
init_state()
if st.session_state.stage == "login":
    page_login()
else:
    try:
        data = load_questions(secret("SHEET_URL"))
    except Exception as e:
        st.error("Could not load the questions.")
        st.caption(str(e))
        st.stop()
    if data.empty:
        st.error("No valid questions were found in the question bank.")
        st.stop()
    stage = st.session_state.stage
    if stage == "setup":
        page_setup(data)
    elif stage == "quiz" and st.session_state.quiz:
        page_quiz()
    elif stage == "result" and st.session_state.quiz:
        page_result()
    else:
        restart()
        st.rerun()
