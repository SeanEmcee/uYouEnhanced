# CircleCI macOS YouTube IPA delivery (PiP Lab)

Status: **CircleCI pipeline #56 progressed through PiP, Return YouTube
Dislikes, SponsorBlock and other tweaks; modern YTUHD then failed because
both libvpx and dav1d header paths were unresolved.** The pinned YTUHD
Makefile now uses its own vendor root, both static decoder archives are
explicitly built and validated on macOS before Theos, and the Linux
preflight checks the rewritten source paths. The build also initializes
the already-required YouMute tweak and corrects FFmpeg staging path case.
Changes are committed, **not yet confirmed by a new macOS build**. Keep
macOS execution disabled until the latest cheap preflight passes.

This does not create a public release, install to a device, or automatically sign
the IPA. The original decrypted YouTube application must be supplied by its
owner from a source they are authorized to use. The build signs no Apple
developer certificate: SideStore signs the resulting IPA for the device.

## Where the code lives

- Repo: `SeanEmcee/uYouEnhanced`
- Branch: `pip-lab-v12`
- CircleCI config: `.circleci/config.yml`
- Build: `Scripts/build_circleci_ipa.sh`
- Validation: `Scripts/verify_ipa.py`
- Secret-safe normalization: `Scripts/normalize_circleci_ipa_url.py`
- Homebrew macOS bootstrap: `Scripts/install_circleci_macos_deps.sh`

The workflow requests CircleCI macOS `m4pro.medium` with Xcode `26.5`,
which matches the project's `iPhoneOS26.5.sdk` target. It retains the
existing PiP/Shorts/player adapter chain, YouPiP, YTUHD, iSponsorBlock,
Cyan injection and final ZIP/dylib verification. It uses the owner's selected
decrypted IPA as the host application, rather than distributing a copyrighted
binary through source control.

## Configure the project once (owner action)

1. In CircleCI, open **Projects** under the correct GitHub-linked organization.
   If `uYouEnhanced` is not yet a CircleCI project, choose **Set Up Project**;
   GitHub App access to all repositories does NOT automatically create projects.
2. Choose the **existing config** at `.circleci/config.yml`. Configure
   **config source branch** and **checkout source branch** as `pip-lab-v12`
   for this development build. Leave automatic push/PR triggers off to avoid
   duplicate credit consumption.
3. Under **Project Settings → Environment Variables**, set the protected
   variable `YOUTUBE_IPA_URL` to the *latest, unexpired HTTPS direct link*
   for your decrypted IPA. It is separate from the GitHub Actions secret of
   the same name. **Never paste the URL in pipeline parameters, GitHub files,
   issues, comments, job output, screenshots or chat.** Update the CircleCI
   value when the provider rotates the URL.
4. Check CircleCI's current **macOS credits** before the first run. A source
   FFmpegKit rebuild may take 30–90+ macOS minutes; setting `build_ffmpeg`
   to `false` avoids that rebuild but may reduce media conversion features
   if no prebuilt frameworks are available.

## Cheap preflight before using a Mac (recommended)

Trigger a manual pipeline on `pip-lab-v12` with `run_ipa_preflight=true`
and `run_ipa_build=false`. This starts a small Linux validation job that
checks Bash syntax and all IPA config/URL regression tests, without
reading or downloading the decrypted IPA and without allocating a macOS VM.
This still consumes a small number of CircleCI credits; check your Free
balance first. The preflight is independent of the macOS build gate.

## Verify the CircleCI URL without using a Mac (after build #3's failure)

Build #3 failed immediately with `Invalid URL characters`. The previous
check rejected even a harmless trailing line break/space in the value stored
as `YOUTUBE_IPA_URL`. The new validator removes ASCII whitespace **only
at the ends** of the URL. It rejects embedded literal whitespace or controls,
a pasted `URL:` label, Markdown wrappers, non-HTTPS schemes, fragments and
credential-bearing hosts. The value and signed query token are never printed.

To check the **actual secret** without downloading or spending macOS credits,
manually trigger the pipeline with `run_ipa_url_check=true` and
`run_ipa_build=false` on `pip-lab-v12`. This creates only a small Linux
job named `ipa-url-check`, which consumes some regular CircleCI compute
credits. If it fails, replace the **CircleCI Project Settings → Environment
Variables → YOUTUBE_IPA_URL** entry with a fresh **single-line, direct HTTPS**
URL. Avoid spaces within the link, quotes, Markdown notation, or `URL:`.
Never paste the URL into CircleCI pipeline parameters, GitHub, chat or logs.

A passing check confirms the source URL **shape**, not that the remote
signed link remains unexpired or that the downloaded IPA is valid.
On the next approved macOS run, the source is downloaded and verified
**before** installing dependencies or compiling, to minimize credit waste.

## Run exactly one build (requires owner approval)

In the existing CircleCI project's **Pipelines → Trigger Pipeline** page,
select the `pip-lab-v12` config and checkout branch and provide these
non-secret pipeline parameters:

| Parameter | Type | Suggested initial value |
| --- | --- | --- |
| `run_ipa_preflight` | Boolean | `false` (run separately first) |
| `run_ipa_url_check` | Boolean | `false` (run separately first) |
| `run_ipa_build` | Boolean | `true` |
| `modern_ytuhd` | Boolean | `true` |
| `build_ffmpeg` | Boolean | `false` for a faster first build, `true` for a full source rebuild |

All three run gates (`run_ipa_preflight`, `run_ipa_url_check`, and `run_ipa_build`) default to **false**.
Setting `run_ipa_build` to `true`
only opens the `approve-youtube-ipa` job. Approve that gate **in CircleCI**
after checking the repo, branch, credit use and secret freshness. Only then
is the macOS `build-youtube-ipa` job scheduled.

No GitHub Actions minutes are used for the CircleCI macOS job.

## Outputs and failure interpretation

On success the job uploads `build-artifacts/` containing:

- `uYouEnhanced_<actual YouTube version>_v3.0.5.ipa`
- Matching `.ipa.sha256` checksum file

The source IPA, URL and signing credentials are not stored as artifacts.
Use the CircleCI job's Artifacts view to retrieve the final IPA, and verify
the SHA-256 checksum before importing to SideStore. **Do not assume artifact
access is private merely because this workflow only publishes on approval: the
GitHub repository is public. Review the CircleCI artifact access permissions.**
Avoid publicly sharing the build artifact URL.

The final file is **unsigned** and device installation is a separate SideStore
signing step. A successful packaging check proves the required tweak dylibs
were included, not that every patched hook behaves correctly on-device.

If the build fails:

- **Download step:** URL expired/redirected or returned invalid ZIP; refresh
  the CircleCI project secret, then approve a new build.
- **Submodule step:** The latest CircleCI macOS attempt downloaded YouTube 21.41.5 but
  failed at `Tweaks/YouTube-X`, which was an orphaned `.gitmodules` entry,
  not a real tracked gitlink. The CircleCI script and manifest now omit it,
  and `test_circleci_ipa_submodules.py` checks the full list against the
  tracked Git index before running a macOS build. Run the cheap
  `run_ipa_preflight=true`, `run_ipa_build=false` workflow to confirm this
  guard before retrying the macOS job. Future submodule failures may instead
  reflect a pinned upstream commit becoming unavailable.
- **Homebrew:** the latest macOS attempt passed the source download,
  all 23 selected gitlink submodules, and the PiP/decoder patch stages, but
  `brew install` exited nonzero. Logs showed multiple failed post-install
  warnings and automatic dependent upgrades (`pyenv`, `ruby-build`), without
  a definitive final Homebrew error. The build now calls
  `Scripts/install_circleci_macos_deps.sh`, which skips installed formulae,
  disables unrelated dependent upgrades, verifies all required formulae
  and commands, and checks that `pipx --version` works. It proceeds past a
  nonzero Homebrew return only when these checks succeed; otherwise it names
  the missing dependency. Run the inexpensive source preflight before
  another macOS build. If the subsequent failure concerns Theos or the SDK,
  compare that step with the original GitHub Actions recipe.
- **Return YouTube Dislikes header compilation:** an October 2026 macOS
  run reached Theos but could not find `YouTubeHeader/YTLikeStatus.h`
  and `YouTubeHeader/YTSettingsCell.h`. The parent Makefile already exports
  `-I$(THEOS_PROJECT_DIR)/Tweaks`; the missing dependency was the tracked
  `Tweaks/YouTubeHeader` submodule, which had not been initialized by the
  CircleCI script. The script now fetches it and calls
  `Scripts/check_circleci_headers.py` before compilation.
  The inexpensive Linux preflight initializes *only* that public submodule,
  verifies both header files and the Makefile include path, and executes
  seven additional offline header regression tests.
  Run that preflight once before approving a new macOS job.
- **FFmpeg:** consider a successful base build first, then explicitly opt into
  the more expensive source compile.
- **Cyan/IPA verification:** do not distribute an incomplete IPA. Capture
  the failing step name and redacted message for a follow-up fix.

## Compilation-surface audit (after first successful RYD compile)

The following macOS failure exposed two errors when compiling
`Tweaks/YouPiP` under the iPhoneOS 26.5 SDK:

- `Settings.x` used the deprecated `UIApplication.keyWindow` property.
  PiP settings now resolve the active `UIWindowScene` key window. Decoder,
  codec and streaming reports in YTUHD have an independent scene-aware
  presenter because YTUHD and YouPiP compile as separate source files.
- Logos `%property` synthesized the PiP edge/recovery accessors at runtime
  but Clang did not see their declarations on `YTPlayerViewController`.
  `apply_lc_playback.py` now inserts a matching Objective-C category
  declaration for the 10 PiP state properties and four custom selectors,
  without changing Logos accessor behavior.

The root Makefile retains third-party deprecation warnings instead of
promoting them to fatal errors. The inexpensive Linux `ipa-recipe-preflight`
now replays all relevant source patch scripts using the pinned YouPiP and RYD
checkouts and the same modern YTUHD source as the macOS workflow. It checks
Logos properties, their compiler declarations, and cross-file presenters.
Linux cannot compile the iOS UIKit code without an Apple SDK, so a passing
rehearsal detects structural errors but **does not guarantee a macOS build**.

Run the Linux preflight on the newest `pip-lab-v12` commit before requesting
another approved macOS build. Use a current, unexpired CircleCI project secret
`YOUTUBE_IPA_URL` only for the actual macOS job.

## Modern YTUHD decoder dependencies and credit protection

Latest failure (CircleCI #56, YouTube 21.41.5): compilation reached
`Tweaks/YTUHD/HAMVPXVideoDecoder.m` and
`Tweaks/YTUHD/HAMDav1dVideoDecoder.m`, which respectively could not find
`vpx/vpx_decoder.h` and `dav1d/dav1d.h`. Both are available in the
pinned libvpx and dav1d vendor gitlinks; nested Theos builds may resolve
the standalone YTUHD `$(THEOS_PROJECT_DIR)` paths to the parent project.

- `Scripts/prepare_circleci_ytuhd.py` rewrites only the temporary modern
  YTUHD Makefile so every vendor include, archive and build script is
  relative to the actual checked-out YTUHD source.
- `Scripts/build_circleci_ytuhd_deps.sh` explicitly constructs both
  ARM64 iPhoneOS decoder archives using upstream vendor scripts and checks
  their existence and architecture **before** the aggregate Theos build.
- `Scripts/ytuhd_source_revision.txt` pins modern YTUHD so low-credit
  Linux preflight and macOS use the same reviewed source revision.
- `tests/test_circleci_ipa_ytuhd.py` and the root-wiring regressions
  validate the include-path rewriting and prevent future missing
  YouMute and wrong-case FFmpeg hook failures.
- Theos may already embed tweaks into its output IPA, so the Cyan stage
  no longer falsely fails when no supplemental `.deb` is generated.
  That case verifies the base IPA's required tweak dylibs instead.

This protects against known structural failures, **not every future
upstream or toolchain failure**. The Linux smoke run cannot produce ARM64
Apple libraries; only an actual Xcode build can validate them. To avoid
wasting macOS credits, manually run `run_ipa_preflight=true` with
`run_ipa_build=false` on `pip-lab-v12` first and inspect any failures.
Do not repeat a paid macOS build until the preflight has passed.

## Safety and operational limitations

This pipeline is deliberately not automatic for current or future repos,
does not use GitHub Bridge's exhausted Actions runners, does not provision
a CircleCI API token, and cannot confirm CircleCI project setup by itself.
Secrets in CircleCI project environments may be accessible to trusted build
jobs: restrict who can modify workflows, who can see artifacts, and which
branches are authorized. A future audited bridge dispatcher still needs a
credentialed CircleCI connection, exact-target approval and receipt tracking
before chat-triggered builds can be claimed.
