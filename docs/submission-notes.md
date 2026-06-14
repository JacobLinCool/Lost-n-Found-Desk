# Build Small submission notes

Official guide checked on 2026-06-14:

- Submit guide: https://build-small-hackathon-field-guide.hf.space/submit
- Field guide, rules, tracks, prizes, FAQ: https://build-small-hackathon-field-guide.hf.space/

## Submission links

- Live Space: https://huggingface.co/spaces/build-small-hackathon/lost-found-desk
- App URL: https://build-small-hackathon-lost-found-desk.hf.space
- Demo video: https://youtu.be/AsOM7K0tL-s
- GitHub repo: https://github.com/JacobLinCool/Lost-n-Found-Desk
- Social post: https://x.com/JacobLinCool/status/2066147773481951378
- Article: https://huggingface.co/spaces/build-small-hackathon/lost-found-desk/blob/main/docs/article.md
- Codex trace dataset: https://huggingface.co/datasets/build-small-hackathon/lost-found-desk-codex-traces
- Agent trace format reference: https://huggingface.co/changelog/agent-trace-viewer
- Hugging Face collection: https://huggingface.co/collections/build-small-hackathon/lost-and-found-desk-6a2ec0551c48861e92dd8443

## Official pre-flight checklist

| Requirement | Status | Evidence / action |
| --- | --- | --- |
| Every model under 32B parameters | Ready | MiniCPM-V 4.6, MiniCPM5-1B, and Nemotron Embed VL are all below the cap. |
| Gradio app in official Build Small HF org | Ready after deploy verification | README front matter uses `sdk: gradio`; target Space is `build-small-hackathon/lost-found-desk`. |
| Demo video | Ready | YouTube is the primary demo link; `demo/lost-found-desk-demo.mp4` remains in the repo as an archived copy. |
| Social post | Ready | Published on X: https://x.com/JacobLinCool/status/2066147773481951378 |
| Zero GPU app limit | Ready | This is one ZeroGPU-targeted Space for the user; still verify account-level count before final form submission if multiple entries exist. |
| README tags | Ready | README contains official tag schema: `track:*`, `sponsor:*`, `achievement:*`. |
| README story / tech write-up | Ready | README explains the problem, users, workflow, architecture, deployment, safety rules, and Codex assistance. |
| Shared agent trace | Ready | Codex-compatible JSONL is published under `traces/` for the official Hugging Face Agent Trace Viewer; public redaction removes local paths, token-shaped strings, and secret-label strings. |

## Quest and challenge eligibility

| Quest / challenge | Eligible? | Requirement | Current status |
| --- | --- | --- | --- |
| Backyard AI | Yes | Practical app improving daily life on local/small models. | Primary track; tagged `track:backyard`. |
| Thousand Token Wood | No | Whimsical / entertainment-first AI-native app. | Not the right framing; this is an operations workflow. |
| Best MiniCPM Build | Yes | Build with MiniCPM models as a core part of the experience. | MiniCPM-V captions photos; MiniCPM5 handles claim intake, matching, and safe message drafting. Tagged `sponsor:openbmb`. |
| Best Use of Codex | Yes | Codex-attributed commits in connected GitHub repo or Space history. | This submission commit includes `Co-authored-by: Codex <codex@openai.com>`. Tagged `sponsor:openai`. |
| Nemotron Hardware Prize | Likely yes | Build with Nemotron models. | Uses `nvidia/llama-nemotron-embed-vl-1b-v2` for retrieval. Tagged `sponsor:nvidia`. |
| Best Use of Modal | No | Use Modal for development or runtime and note it in README. | Project does not use Modal. |
| Off the Grid | Yes | No cloud model APIs; local/open model runtime. | No hosted model API dependency. Tagged `achievement:offgrid`. |
| Well-Tuned | No | Use a fine-tuned model published on Hugging Face. | No fine-tuned model. |
| Off-Brand | Yes | Custom UI beyond default Gradio. | Svelte UI served through Gradio Server. Tagged `achievement:offbrand`. |
| Llama Champion | No | Model runs through llama.cpp. | Uses Transformers/Sentence Transformers, not llama.cpp. |
| Sharing is Caring | Yes | Shared agent trace on the Hub. | Official-format Codex JSONL trace published at https://huggingface.co/datasets/build-small-hackathon/lost-found-desk-codex-traces and grouped in the collection. Tagged `achievement:sharing`. |
| Field Notes | Yes | Blog/report about what was built and learned. | `docs/article.md`, this notes file, and `ARTICLE.md`. Tagged `achievement:fieldnotes`. |
| Tiny Titan | Yes by prize-table criteria | Every model is <= 4B parameters. | Documented in README; official submit tag generator does not expose a `tiny` tag. |
| Best Demo | Ready | Strong app + demo video + social post. | Demo video and published X post are linked from README and notes. |
| Best Agent | No / weak | Multi-step tool use and planning. | The app has planner-guided intake, but it is not primarily an agentic tool-use app. |

## Repository hygiene

- `.env`, `.env.*`, `.venv`, `node_modules`, build caches, runtime DB, runtime uploads, and `output/` scratch recordings are ignored.
- `.env.example` is kept as a safe configuration template.
- Final frontend build in `static/` is intentionally committed because the Space should not require a Node build step.
- Final demo video is intentionally committed at `demo/lost-found-desk-demo.mp4`.

## Remaining manual items

- Open the official submit page, enter `lost-found-desk`, verify tags, and submit the form.

## Final submission summary

Lost & Found Desk is a caption-first lost-and-found return desk for event venues, conferences, gyms, schools, and coworking spaces. Staff photograph one item at a time; MiniCPM-V captions each item; claimants report lost items through a private multilingual assistant; MiniCPM5 and Nemotron Embed help staff narrow candidate matches; and staff confirm every handoff offline. It is a practical Backyard AI app with a custom Svelte UI on Gradio Server, no hosted model API dependency, all models below the 32B cap, Codex-attributed development commits, a public official-format Codex trace dataset for the HF Agent Trace Viewer, and a Hugging Face collection that groups the Space, models, article link, and dataset.
