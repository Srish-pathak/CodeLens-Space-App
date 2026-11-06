import os
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="CodeLens · Space Code Analyser", page_icon="🪐", layout="wide")

from complexity import analyze_complexity
from github_fetcher import GitHubFetchError, fetch_public_repository
from report import build_json_report, build_markdown_report, build_repo_markdown
from reviewer import get_secret, probe_deepseek_connectivity, review_code, review_repo_files
from theme import (
    banner, finding_card, hero, inject_css, rank_badge, score_ring, stat_row, tip_card,
)
from utils import LANGUAGE_CONFIG, score_label

try:
    from streamlit_ace import st_ace
    HAS_ACE = True
except ImportError:
    HAS_ACE = False

SAMPLES = {
    "Python": (
        "import os, sys\n\n"
        "def total(items, discount=[]):\n"
        "    try:\n"
        "        return sum(items) - sum(discount)\n"
        "    except:\n"
        "        pass\n\n"
        "def run(cmd):\n"
        "    eval(cmd)\n\n"
        "api_key = \"sk_live_1234567890abcdef\"\n"
        "print(total([1, 2, 3], 4, 5))\n"
    ),
    "C++": "#include <cstring>\nint add(int a, int b) {\n    char buf[8];\n    strcpy(buf, \"too long for this buffer\");\n    return a+b;\n}\n",
    "Java": "public class Demo {\n    int add(int a, int b) {\n        try { return a / b; }\n        catch (Exception e) { return 0; }\n    }\n}\n",
    "JavaScript": "var count = 0;\nfunction add(a, b) {\n    if (a == b) console.log('same');\n    return a + b;\n}\ndocument.body.innerHTML = location.hash;\n",
    "JSX": "function Greeting({ name }) {\n    return <h1 dangerouslySetInnerHTML={{__html: name}} />;\n}\n",
    "TypeScript": "function add(a: number, b: number): number {\n    return a + b;\n}\n",
    "TSX": "function Greeting({ name }: { name: string }) {\n    return <h1>Hello, {name}</h1>;\n}\n",
    "HTML": "<main>\n    <h1>Hello</h1>\n</main>\n",
    "CSS": "main {\n    color: navy;\n}\n",
    "SCSS": "$primary: navy;\n\nmain {\n    color: $primary;\n}\n",
}
EXT_TO_LANGUAGE = {cfg["ext"]: name for name, cfg in LANGUAGE_CONFIG.items()}
EXT_TO_LANGUAGE.update({".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".h": "C++"})

DEFAULT_STATE = {
    "review_result": None,
    "complexity_result": None,
    "reviewed_code": "",
    "reviewed_language": "Python",
    "repository_result": None,
    "code_text": SAMPLES["Python"],
    "editor_version": 0,
    "language": "Python",
    "history": [],
}
for key, value in DEFAULT_STATE.items():
    st.session_state.setdefault(key, value)

inject_css()


# ---------- callbacks (run before the script reruns, so widget state may be set) ----------
def load_sample() -> None:
    st.session_state.code_text = SAMPLES[st.session_state.language]
    st.session_state.editor_version += 1


def handle_upload() -> None:
    uploaded = st.session_state.get("uploaded_file")
    if uploaded is None:
        return
    extension = os.path.splitext(uploaded.name)[1].lower()
    language = EXT_TO_LANGUAGE.get(extension)
    try:
        text = uploaded.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        st.session_state.upload_error = "That file is not valid UTF-8 text."
        return
    st.session_state.upload_error = None
    st.session_state.code_text = text
    if language:
        st.session_state.language = language
    st.session_state.editor_version += 1


def clear_results() -> None:
    st.session_state.review_result = None
    st.session_state.complexity_result = None


def key_status(name: str) -> bool:
    return bool(os.getenv(name) or get_secret(name))


# ---------- sidebar ----------
with st.sidebar:
    st.markdown("## 🛰️ Mission Control")
    language = st.selectbox("Language", list(LANGUAGE_CONFIG.keys()), key="language")
    ai_provider = st.selectbox(
        "AI provider", ["DeepSeek", "Gemini"], index=0,
        help="Offline checks always run. The AI provider adds a deeper review when a key is configured.",
    )
    enable_fallback = st.checkbox(
        "Fall back to Gemini if DeepSeek fails", value=False, disabled=ai_provider != "DeepSeek"
    )
    st.markdown("### 📡 Signal status")
    for label, env_name in (("DeepSeek", "DEEPSEEK_API_KEY"), ("Gemini", "GEMINI_API_KEY")):
        st.markdown("{} **{}**".format("🟢" if key_status(env_name) else "⚪", label) +
                    (" key found" if key_status(env_name) else " no key (offline mode)"))
    if ai_provider == "DeepSeek" and st.button("Test DeepSeek connection", use_container_width=True):
        probe = probe_deepseek_connectivity()
        if probe["connected"]:
            st.success("Connected · model {}".format(probe["model"]))
        else:
            st.error(probe["error"])
    st.markdown("---")
    st.markdown("### 🕰️ Recent scans")
    if not st.session_state.history:
        st.caption("Your scans this session will appear here.")
    for entry in reversed(st.session_state.history[-6:]):
        st.caption("`{}` · {} findings · {}".format(entry["language"], entry["findings"], entry["time"]))
    st.markdown("---")
    st.caption("Set `DEEPSEEK_API_KEY` or `GEMINI_API_KEY` as an environment variable or Streamlit secret.")

hero("CODELENS", "Scan code across the galaxy · static analysis + AI review · GitHub orbit mode")

tab_scan, tab_repo = st.tabs(["🚀 Code Scanner", "🪐 GitHub Orbit"])


# ====================================================================== scanner
with tab_scan:
    left, right = st.columns([3, 1])
    with right:
        st.file_uploader(
            "Upload a source file",
            type=[e.lstrip(".") for e in EXT_TO_LANGUAGE],
            key="uploaded_file",
            on_change=handle_upload,
        )
        if st.session_state.get("upload_error"):
            st.error(st.session_state.upload_error)
        st.button("✨ Load sample code", on_click=load_sample, use_container_width=True)
    with left:
        if HAS_ACE:
            code_input = st_ace(
                value=st.session_state.code_text,
                language=LANGUAGE_CONFIG[language]["ace_mode"],
                theme="tomorrow_night",
                font_size=14,
                height=330,
                key="editor_{}_{}".format(language, st.session_state.editor_version),
            )
        else:
            code_input = st.text_area(
                "Source code", value=st.session_state.code_text, height=330,
                key="textarea_{}".format(st.session_state.editor_version),
            )
        if code_input is not None:
            st.session_state.code_text = code_input

    run_col, clear_col, _ = st.columns([1.4, 1, 4])
    run_clicked = run_col.button("🚀 Launch scan", type="primary", use_container_width=True)
    clear_col.button("Clear", on_click=clear_results, use_container_width=True)

    if run_clicked:
        source = st.session_state.code_text
        if not source or not source.strip():
            st.warning("Add some code first, paste it, upload a file, or load the sample.")
        else:
            os.environ["AUTO_AI_FALLBACK"] = "true" if enable_fallback else "false"
            with st.spinner("Scanning your code through the cosmos..."):
                result = review_code(source, language, "<input>", ai_provider.lower())
                st.session_state.review_result = result
                st.session_state.reviewed_code = source
                st.session_state.reviewed_language = language
                st.session_state.complexity_result = (
                    analyze_complexity(source, language) if LANGUAGE_CONFIG[language]["supports_radon"] else None
                )
            st.session_state.history.append({
                "language": language,
                "findings": len(result.get("bugs", [])),
                "time": datetime.now().strftime("%H:%M"),
            })

    result = st.session_state.review_result
    complexity = st.session_state.complexity_result

    if not result:
        st.markdown(
            '<div class="panel" style="text-align:center;margin-top:1rem">'
            "<b>Ready for launch.</b> Paste code, upload a file or load a sample, then hit "
            "<b>Launch scan</b>. Offline checks work with no API key.</div>",
            unsafe_allow_html=True,
        )
    else:
        ai_status = result.get("analysis_status", {}).get("ai", "unknown")
        ai_ok = ai_status == "completed"
        bugs = [b for b in result.get("bugs", []) if isinstance(b, dict)]
        improvements = [i for i in result.get("improvements", []) if isinstance(i, dict)]
        severe = sum(1 for b in bugs if str(b.get("severity", "")).lower() in {"critical", "high"})
        warns = sum(1 for b in bugs if str(b.get("severity", "")).lower() in {"warning", "medium"})
        score = result.get("overall_score", 0)

        st.markdown("### Mission report")
        if ai_ok and result.get("summary"):
            banner(result["summary"], "info")
        elif not ai_ok:
            banner(
                "AI review: {}. Offline static analysis is shown below.".format(
                    ai_status.replace("_", " ")), "warn")
        stat_row([
            ("Health score", "{}/10".format(round(score, 1)) if ai_ok else "—", score_label(score) if ai_ok else "AI offline", "#34d399"),
            ("Critical / high", severe, "needs attention", "#fb7185"),
            ("Warnings", warns, "worth fixing", "#fbbf24"),
            ("Suggestions", len(improvements), "improvements", "#8b5cf6"),
            ("Avg complexity", (complexity or {}).get("average_complexity", "—"), "rank {}".format((complexity or {}).get("rating", "—")), "#22d3ee"),
        ])
        st.markdown("")

        t_find, t_imp, t_cx, t_score, t_diff, t_export = st.tabs(
            ["🐛 Findings", "💡 Improvements", "⚙️ Complexity", "📊 Score", "🔀 Before / After", "📦 Export"]
        )

        with t_find:
            levels = st.multiselect(
                "Filter by severity", ["critical", "high", "warning", "medium", "low", "info"],
                default=["critical", "high", "warning", "medium", "low", "info"],
            )
            shown = [b for b in bugs if str(b.get("severity", "info")).lower() in levels]
            if not shown:
                banner("No findings match. Clear skies! ✅" if ai_ok or not bugs else
                       "No offline findings. AI findings are unavailable.", "ok")
            for bug in shown:
                st.markdown(finding_card(bug), unsafe_allow_html=True)

        with t_imp:
            if not improvements:
                banner("No specific improvements were suggested.", "info")
            for tip in improvements:
                st.markdown(tip_card(tip), unsafe_allow_html=True)

        with t_cx:
            if complexity and not complexity.get("error"):
                st.markdown("**Maintainability index:** {}".format(complexity.get("maintainability_index", "N/A")))
                if complexity.get("details"):
                    rows = "".join(
                        "<tr><td style='padding:.35rem .8rem'><code>{}</code></td>"
                        "<td style='padding:.35rem .8rem'>{}</td><td style='padding:.35rem .8rem'>{}</td></tr>".format(
                            d["name"].replace("<", "&lt;"), d["complexity"], rank_badge(d["rank"]))
                        for d in complexity["details"]
                    )
                    st.markdown(
                        "<div class='panel'><table style='width:100%'><tr style='color:#8f96c7;text-align:left'>"
                        "<th>Function</th><th>Complexity</th><th>Rank</th></tr>{}</table></div>".format(rows),
                        unsafe_allow_html=True,
                    )
            elif complexity and complexity.get("error"):
                banner(complexity["error"], "warn")
            else:
                banner("Cyclomatic complexity (Radon) is available for Python only.", "info")
            if result.get("complexity_notes") and result["complexity_notes"] != "N/A":
                st.caption(result["complexity_notes"])

        with t_score:
            if ai_ok:
                st.markdown(score_ring(score, score_label(score)), unsafe_allow_html=True)
            else:
                banner("The AI score needs a completed AI review. Add an API key in your environment to enable it.", "info")

        with t_diff:
            improved = result.get("improved_code", "")
            if improved:
                a, b = st.columns(2)
                a.markdown("**Original**")
                a.code(st.session_state.reviewed_code, language=st.session_state.reviewed_language.lower())
                b.markdown("**AI-improved**")
                b.code(improved, language=st.session_state.reviewed_language.lower())
            else:
                banner("No improved version was returned.", "info")

        with t_export:
            reviewed_language = st.session_state.reviewed_language
            c1, c2 = st.columns(2)
            c1.download_button(
                "⬇️ Markdown report",
                build_markdown_report(result, complexity, reviewed_language, st.session_state.reviewed_code),
                file_name="codelens_report.md", mime="text/markdown", use_container_width=True,
            )
            c2.download_button(
                "⬇️ JSON data", build_json_report(result, complexity),
                file_name="codelens_report.json", mime="application/json", use_container_width=True,
            )


# ====================================================================== repository
with tab_repo:
    st.caption(
        "Analyse supported source files from a public GitHub repository. Files are sent to the selected AI "
        "provider when a key is configured; don't submit code you aren't permitted to share."
    )
    url_col, btn_col = st.columns([4, 1])
    repository_url = url_col.text_input(
        "Public repository URL", placeholder="https://github.com/owner/repository", key="repository_url",
        label_visibility="collapsed",
    )
    analyze_clicked = btn_col.button("🪐 Analyse repo", type="primary", use_container_width=True)

    if analyze_clicked:
        if not repository_url.strip():
            st.warning("Enter a public GitHub repository URL first.")
        else:
            try:
                with st.spinner("Contacting GitHub..."):
                    repository_data = fetch_public_repository(repository_url)
                if not repository_data["files"]:
                    st.session_state.repository_result = None
                    st.warning("No supported, readable source files were found in this repository.")
                else:
                    os.environ["AUTO_AI_FALLBACK"] = "true" if enable_fallback else "false"
                    progress = st.progress(0.0, text="Preparing file reviews...")
                    current = st.empty()

                    def update_progress(done, total, path):
                        progress.progress(done / total, text="Reviewed {}/{} files".format(done, total))
                        current.caption("Scanning: {}".format(path))

                    review_data = review_repo_files(repository_data["files"], update_progress, ai_provider.lower())
                    progress.empty()
                    current.empty()
                    st.session_state.repository_result = {"repository": repository_data, "review": review_data}
            except GitHubFetchError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error("Repository review could not be completed: {}".format(exc))

    repo_result = st.session_state.repository_result
    if not repo_result:
        st.markdown(
            '<div class="panel" style="text-align:center;margin-top:1rem">Enter a repository to begin an orbit scan.</div>',
            unsafe_allow_html=True,
        )
    else:
        repo = repo_result["repository"]
        review = repo_result["review"]
        st.markdown("### [{}]({}) · `{}`".format(repo["full_name"], repo["html_url"], repo["branch"]))
        if repo.get("description"):
            st.caption(repo["description"])
        stat_row([
            ("Source files", repo["source_files_detected"], "detected", "#22d3ee"),
            ("Reviewed", review["files_reviewed"], "files", "#8b5cf6"),
            ("Critical / high", review["critical_bugs"], "findings", "#fb7185"),
            ("Warnings", review["warnings"], "findings", "#fbbf24"),
            ("Quality", "{}/10".format(review["overall_score"]) if review["overall_score"] is not None else "N/A",
             score_label(review["overall_score"]) if review["overall_score"] is not None else "AI offline", "#34d399"),
        ])
        st.markdown("")
        if repo.get("files_limited"):
            banner("Review is capped at 30 files. Pick a smaller repo or subfolder for full coverage.", "info")
        if repo.get("tree_truncated"):
            banner("GitHub returned a truncated tree; the detected file count may be incomplete.", "warn")
        if review.get("failed_files"):
            banner("{} file(s) could not be reviewed.".format(review["failed_files"]), "warn")
        if review.get("ai_failed_files"):
            banner("{} file(s) have offline analysis only; AI review was unavailable.".format(review["ai_failed_files"]), "warn")
        if repo.get("fetch_errors"):
            with st.expander("Files skipped during download ({})".format(len(repo["fetch_errors"]))):
                for item in repo["fetch_errors"]:
                    st.write("**{}**: {}".format(item["path"], item["error"]))

        all_bugs, all_tips = [], []
        for file_result in review["file_results"]:
            all_bugs += [(file_result["path"], b) for b in file_result["review"].get("bugs", []) if isinstance(b, dict)]
            all_tips += [(file_result["path"], i) for i in file_result["review"].get("improvements", []) if isinstance(i, dict)]

        r_find, r_imp, r_files, r_export = st.tabs(["🐛 Bugs & security", "💡 Improvements", "📁 File explorer", "📦 Export"])
        with r_find:
            if not all_bugs:
                banner("No findings reported in the reviewed files. ✅", "ok")
            for path, bug in all_bugs:
                st.markdown(finding_card(bug, path), unsafe_allow_html=True)
        with r_imp:
            if not all_tips:
                banner("No improvement suggestions were returned.", "info")
            for path, tip in all_tips:
                st.markdown(tip_card(tip, path), unsafe_allow_html=True)
        with r_files:
            paths = [f["path"] for f in review["file_results"]]
            selected_path = st.selectbox("Select a reviewed file", paths)
            selected = next(f for f in review["file_results"] if f["path"] == selected_path)
            st.caption("Language: {}".format(selected["language"]))
            st.code(selected["content"], language=selected["language"].lower())
            file_review = selected["review"]
            st.markdown("**Summary**")
            st.write(file_review.get("summary") or "No summary returned.")
            for bug in [b for b in file_review.get("bugs", []) if isinstance(b, dict)]:
                st.markdown(finding_card(bug), unsafe_allow_html=True)
            for tip in [i for i in file_review.get("improvements", []) if isinstance(i, dict)]:
                st.markdown(tip_card(tip), unsafe_allow_html=True)
            fc = selected.get("complexity")
            if selected["language"] == "Python" and fc and not fc.get("error"):
                st.markdown("**Complexity:** average {} (rank {}) · maintainability {}".format(
                    fc.get("average_complexity"), fc.get("rating"), fc.get("maintainability_index")))
                if fc.get("details"):
                    st.table(fc["details"])
            if file_review.get("improved_code"):
                with st.expander("AI-generated improved version"):
                    st.code(file_review["improved_code"], language=selected["language"].lower())
        with r_export:
            st.download_button(
                "⬇️ Repository report (Markdown)", build_repo_markdown(repo, review),
                file_name="codelens_repo_report.md", mime="text/markdown",
            )
