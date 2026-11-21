# AI Disclosure: Team SAM, Track 3 (Path Finder)

We used an AI coding assistant (Anthropic's Claude, through Claude Code) during this project. Below is what it was used for and what the team did.

## Where AI was used

| Area | How AI helped | Team's role |
| --- | --- | --- |
| Algorithm code (`src/main.py`) | Drafted and refactored pipeline stages; proposed and ran parameter sweeps; helped debug | Set the approach, chose what to keep, reviewed every change, ran and checked all results |
| Tooling (`tools/`) | Wrote scripts for data download, the damage generator, scoring, plotting and tuning | Defined what to measure; checked scores against ground truth |
| Documentation | Helped write the README, organiser questions and the presentation text | Reviewed and edited for accuracy |
| Demo video | Generated the animated video (HyperFrames, HTML/GSAP) and its soundtrack from our real data and figures | Directed the story, the style and every revision |

## What was not AI-generated

- The data: EuRoC MAV and TUM-VI public datasets, damaged with the organisers' `degrade_imu.py`.
- The ground truth and the numbers: every result was measured by running our code on that data.

## Guarantees

- The submitted trajectory (`estimated_trajectory.txt`) is produced only by `src/main.py`.
- That script is deterministic and depends only on NumPy. No AI model runs at inference time.
- All numbers in the README, slides and video come from our scoring scripts (`tools/score.py`, `tools/evalall.py`).
