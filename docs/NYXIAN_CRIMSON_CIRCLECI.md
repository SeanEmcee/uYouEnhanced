# Nyxian Crimson Red Apple — CircleCI Xcode build

Branch: `nyxian-crimson-circleci`
Repo: `SeanEmcee/uYouEnhanced` (isolated CI build branch only, **not** the YouTube branch)
Source: `emexlab/Nyxian` pinned commit `350dd8dbeb796bc0ff5bc91ef770f1a2994432e7`
Output: unsigned Nyxian IPA with compiled default/alternate Crimson icon sets.

## Scope
The existing YouTube IPA is unaffected. This is a **Nyxian host-app icon rebuild**, not the Procursus ROM archive. The Crimson ROM v1.2 ZIP remains separate. Preserve the old Nyxian app while testing. Sign the output using an authorized device-side signing workflow.

## Setup
1. Select this branch as the **CircleCI config source AND checkout source** for a separate pipeline. Do not change the working YouTube project config branch globally without checking its existing workflows. The safest long-term setup is a dedicated CircleCI project/repo.
2. Upload the accompanying `approved-assets.zip` from the local bundle to an HTTPS-hosted private file location accessible from CircleCI (Cloudflare R2 works). Configure the URL as the CircleCI project environment variable `CRIMSON_ASSET_URL`. Do not put expiring signed URLs, credentials or query tokens in GitHub files or pipeline parameters. The script does not print the URL and verifies the downloaded bytes against the checked-in SHA-256.
3. Trigger **run_crimson_preflight=true** and all other run parameters false. This runs Linux only.
4. Trigger **run_crimson_build=true** and all other run parameters false. Approve the `approve-crimson-build` gate after checking expected macOS credits. This executes on macOS Xcode 26.5.
5. Download the unsigned IPA and matching .sha256 from the CircleCI Artifacts view, verify the checksum and sign with your chosen authorized signer.

The workflow defaults OFF, so pushes do not schedule expensive builds.
It cannot run until CircleCI is configured with the approved asset URL and the user approves a build.
Build success proves compilation/IPA packaging, **not** on-device runtime success.
