# Before You Install — Agreement Required

Aegis MemoryAgent asks you to read and agree to a short set of terms **before first use**. The
agent will not run its main loop until you accept (see the consent gate in
`memoryagent.policy`).

By installing and running this Software, you confirm that you have read and agree to:

1. **MIT License** — [`LICENSE`](LICENSE)
2. **Terms of Service** — [`docs/legal/TERMS_OF_SERVICE.md`](docs/legal/TERMS_OF_SERVICE.md)
3. **Acceptable Use Policy** — [`docs/legal/ACCEPTABLE_USE_POLICY.md`](docs/legal/ACCEPTABLE_USE_POLICY.md)
4. **Privacy Policy** — [`docs/legal/PRIVACY_POLICY.md`](docs/legal/PRIVACY_POLICY.md)
5. **AI Output & Warranty Disclaimer** — [`docs/legal/DISCLAIMER.md`](docs/legal/DISCLAIMER.md)

You specifically acknowledge that:

- ✅ You will use the Software **only for lawful purposes**, complying with **U.S. federal law
  and the laws of your own state and locality** (and any other law that applies to you).
- ✅ You will **not** use it to generate sexual content, nudity, explicit adult role-play, or
  any sexualization of minors, or for any other use prohibited by the Acceptable Use Policy.
- ✅ You understand the **AI output may be wrong** and is **not professional advice**; a human
  reviews and owns every consequential decision.
- ✅ The Software is provided **"as is", with no warranty**, and your use is at your own risk.

**How acceptance is recorded:** on first run the CLI/app shows a summary and asks you to type
`AGREE`. Your acceptance (with timestamp and policy version) is written to a local file in your
config/memory directory. You can withdraw consent at any time by stopping use and deleting that
file and your memory store. Set `AEGIS_ASSUME_CONSENT=1` only in automated/CI contexts where
you have already accepted these terms on behalf of the operator.
