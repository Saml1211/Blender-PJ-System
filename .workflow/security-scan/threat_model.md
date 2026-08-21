# Blender-PJ-System security threat model

## Overview

Blender-PJ-System is a local Blender 4.2 extension for engineering layout of
projectors against analytic cylindrical walls. Its primary runtime is Blender's
embedded Python interpreter. The add-on registers UI panels and operators,
reads and mutates the current `.blend`, creates meshes, cameras, materials and
collections, and performs pure in-process geometry and photometry calculations.
It has no server, authentication boundary, database, network client, subprocess
launcher, native extension, or runtime third-party dependency.

## Threat Model, Trust Boundaries, and Assumptions

- The Blender operator controls the workstation, installed extension archive,
  and current scene. Local Python code and a deliberately installed add-on are
  trusted at the same privilege level as Blender itself.
- `.blend` contents, object names, transforms, custom properties and numeric UI
  inputs may originate from an untrusted or malformed project file. The add-on
  must turn invalid values into bounded errors and must not delete user-owned
  scene data merely because names collide.
- The extension zip and repository checkout cross a developer-to-user supply
  chain boundary. Packaging must contain only intended source, a valid manifest,
  no secrets, dependency trees, logs or local agent configuration.
- GitHub Actions crosses a repository-to-hosted-runner boundary. Workflow input
  is repository-controlled; CI should use least privilege, bounded downloads and
  no repository secrets.
- Correctness failures can create costly engineering decisions even when they
  are not conventional confidentiality or code-execution vulnerabilities.
  Security findings remain distinct from calculation-quality defects.

Security objectives are: preserve user scene ownership; reject malformed and
non-finite geometry safely; avoid implicit file/network/process operations;
ship a deterministic auditable extension archive; and keep CI read-only except
for ephemeral build output.

## Attack Surface, Mitigations, and Attacker Stories

- Blender operators in `operators.py` consume scene data and numeric properties.
  Relevant classes are denial of service through pathological values, unsafe
  mutation of unrelated objects, and state corruption across registration.
- `visualization.py` creates and deletes Blender datablocks. Ownership tagging,
  dedicated collections and object-level deletion guards are the primary
  controls against destructive name collisions.
- `core/` consumes numbers and vectors. Finite/range validation and bounded grid,
  sample and iteration limits constrain malformed-project denial of service.
- `blender_manifest.toml` and CI define the distributable boundary. The manifest
  requests no permissions and the runtime has no imports for network, shell,
  dynamic evaluation, deserialization or credential access.
- Documentation and historical source are not executable runtime surfaces.
  Blender's own parser, Python console, arbitrary scripts and malicious third-
  party add-ons are outside this repository's security boundary.

## Severity Calibration (Critical, High, Medium, Low)

- **Critical:** a distributed archive executing attacker-controlled code on
  installation, credential theft, or CI secret exfiltration. No legitimate
  feature requires those capabilities.
- **High:** add-on actions deleting or overwriting arbitrary user scene/files,
  or a crafted `.blend` reaching arbitrary code execution through this add-on.
- **Medium:** reliable crafted-scene denial of service, unbounded resource use,
  or cross-scene mutation beyond owner-tagged generated content.
- **Low:** noisy failures, stale generated data, or package metadata weaknesses
  without a credible privilege, confidentiality or destructive-data impact.

Repository: https://github.com/Saml1211/Blender-PJ-System
Version: working-tree-bf4cbd50-b7806a22
