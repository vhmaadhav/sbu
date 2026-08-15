"""Study Buddy homepage (Streamlit). Run with:  streamlit run app.py"""
import time
from pathlib import Path

import streamlit as st

from core import db, flashcards, llm, rag
from core.config import INBOX_DIR
from core.ingest import start_worker

st.set_page_config(page_title="Study Buddy", page_icon="📚", layout="wide")


@st.cache_resource
def _boot():
    db.init_db()
    return start_worker()


_boot()

st.title("📚 Study Buddy")
if not llm.is_available():
    st.warning("LM Studio is not reachable — start it and load a model. "
               "Captures still queue up and will process once it's back.")

tab_library, tab_upload, tab_ask, tab_audio = st.tabs(
    ["Library", "Upload", "Ask My Notes", "Audiobook"]
)

with tab_library:
    subjects = db.list_subjects()
    if not subjects:
        st.info("Nothing here yet — upload something or use the overlay buddy.")
    for subj in subjects:
        with st.expander(f"📁 {subj['name']}", expanded=False):
            for item in db.list_items(subj["id"]):
                st.markdown(f"**{item['title'] or item['filename']}** "
                            f"· {item['kind']} · {item['status']}")
                for note in db.notes_for_item(item["id"]):
                    st.markdown(note["markdown"])
                st.caption(f"Source file: {item['stored_path']}")
                st.divider()

with tab_upload:
    uploads = st.file_uploader(
        "Drop lectures, recordings, PDFs, slides or screenshots",
        accept_multiple_files=True,
        type=["wav", "mp3", "m4a", "mp4", "mov", "mkv", "pdf", "png", "jpg", "jpeg", "txt", "md"],
    )
    if uploads and st.button("Add to queue"):
        for up in uploads:
            dest = INBOX_DIR / f"upload_{int(time.time()*1000)}_{up.name}"
            dest.write_bytes(up.getbuffer())
        st.success(f"Queued {len(uploads)} file(s).")

    st.subheader("Processing queue")
    items = db.list_items()
    if items:
        for item in items[:25]:
            icon = {"pending": "⏳", "processing": "⚙️", "done": "✅", "error": "❌"}.get(item["status"], "•")
            line = f"{icon} {item['filename']} — {item['status']}"
            if item["status"] == "error":
                line += f" ({item['error']})"
            st.text(line)
        if any(i["status"] in ("pending", "processing") for i in items):
            st.button("Refresh")
    else:
        st.caption("Queue is empty.")

with tab_ask:
    subjects = db.list_subjects()
    subject = st.selectbox(
        "Subject filter", ["All subjects"] + [s["name"] for s in subjects]
    )
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for role, content in st.session_state.chat:
        st.chat_message(role).markdown(content)
    if question := st.chat_input("Ask anything about your notes…"):
        st.chat_message("user").markdown(question)
        st.session_state.chat.append(("user", question))
        with st.chat_message("assistant"):
            with st.spinner("Working on your request…"):
                selected_subject = None if subject == "All subjects" else subject
                result = flashcards.maybe_create_from_chat(question, selected_subject)
                if result is None:
                    result = rag.ask(question, selected_subject)
            st.markdown(result["answer"])
            if result["sources"]:
                st.caption("Sources: " + " · ".join(s["label"] for s in result["sources"]))
            for img in result["images"]:
                if Path(img).exists():
                    st.image(img, width=400)
            if result.get("deck_id"):
                deck = db.get_flashcard_deck(result["deck_id"])
                if deck:
                    with st.expander("Preview the new deck", expanded=True):
                        for card in deck["cards"]:
                            st.markdown(f"**{card['front']}**  \n{card['back']}")
        st.session_state.chat.append(("assistant", result["answer"]))

with tab_audio:
    subjects = db.list_subjects()
    if not subjects:
        st.info("Generate some notes first — then turn them into an audiobook.")
    else:
        subj_name = st.selectbox("Subject", [s["name"] for s in subjects], key="ab_subj")
        subj = next(s for s in subjects if s["name"] == subj_name)
        notes = db.notes_for_subject(subj["id"])
        if not notes:
            st.info("No notes in this subject yet.")
        else:
            options = {f"{n['title'] or 'Untitled'} (note {n['id']})": n for n in notes}
            picked = st.multiselect("Notes to narrate", list(options), default=list(options)[:1])
            if picked and st.button("🎧 Generate audiobook"):
                from core.audiobook import generate
                combined = "\n\n".join(options[p]["markdown"] for p in picked)
                with st.spinner("Writing the narration and synthesizing with Kokoro…"):
                    path = generate(combined, subj_name)
                st.success(f"Saved {path.name}")
                st.audio(str(path))

        st.subheader("Previous audiobooks")
        from core.config import AUDIOBOOKS_DIR
        for wav in sorted(AUDIOBOOKS_DIR.glob("*.wav"), reverse=True)[:10]:
            st.markdown(f"**{wav.name}**")
            st.audio(str(wav))
