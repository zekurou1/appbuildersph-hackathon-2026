# Independent pilot protocol

Status: **not conducted**. Automated synthetic tests and the builder's observations do not count as independent user validation. Do not mark this gate passed until a separate participant completes tasks and their results are recorded.

Use an eligible Windows 11 x64 machine and a synthetic or explicitly consented folder. Start with the synthetic development corpus; `scripts/evaluate.py` creates an isolated copy under ignored runtime reports. Do not share private originals or index databases in GitHub reports. The participant can use their own small folder locally with permission, without uploading it.

## Session

1. Record anonymous participant code, Windows version, CPU/RAM, package hash and model revision. Explain selected-folder indexing, plaintext derivatives, manual refresh, OCR limitations and originals remaining untouched. Ask permission before indexing personal files; synthetic files require no personal-file consent.
2. Give six tasks: rental-deposit conditions, timetable screenshot, exact receipt code among similar codes, unfamiliar wording, absent target and recently modified file. The participant writes their own queries. Do not suggest the query, correct filename or result before they finish.
3. Alternate which baseline comes first across participants: Words only then Meaning + words, or the reverse. Use equivalent tasks rather than repeating a learned target. Record time to correct original, wrong opens, result chosen, whether evidence was inspected and whether the task was completed without assistance.
4. Ask the participant to refresh a changed file, review a failed image, remove a folder and restart. Verify the removed folder cannot be searched, previews are cleared and originals remain intact.
5. Test keyboard navigation, largest text, and Narrator if the participant is comfortable using it. Record obstacles verbatim only with consent; do not invent quotes. Mark a screen-reader check unperformed when it was not performed.

Stop on a privacy violation, repeated wrong-file action, crash or unsupported setup. Preserve local diagnostic counts/error codes; do not publish participant names, queries, paths or original contents without explicit consent.

## Result template

Copy this header into a local CSV outside tracked source:

```csv
participant_code,package_sha256,task_code,mode,correct_file_opened,time_seconds,wrong_opens,evidence_inspected,assistance_needed,issue_code
```

Every row must represent an observed attempt. Missing measurements stay blank. Report participant count and completed task count alongside results. Do not turn builder-created labels or automated task success into user acceptance. A practical first pilot can use 3-5 independent participants; that is a proposed sample, not a claim that recruitment or testing occurred.

## Another-machine acceptance

On a separate Windows 11 x64 computer, start from the distribution with no project Python or repository on PATH. Launch from an unrelated working directory, index a new PDF/TXT and readable English screenshot, search from a new description, inspect evidence and open/reveal the original. Check missing OCR/language recovery, refresh, clear, restart and uninstall preserving originals. Record OS/build, English OCR availability and exact package hash. A GitHub Windows Server runner is additional executable evidence, not a substitute for Windows 11 user testing.
