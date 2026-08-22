# PIX User Guide

This directory contains task-oriented documentation for people and AI agents
using the public PIX API.

## Guides

- [Reading and Inspecting OCEL 2.0 Logs](OCEL_READING_GUIDE.md)

## Maintenance rule

The user guide is part of the public API baseline. Update the relevant guide
whenever a release changes any of the following:

- public function, class, property, exception, or warning behavior;
- supported input format or compatibility boundary;
- default normalization or assumption policy;
- diagnostic fields returned to users or AI agents;
- installation requirements or runnable examples.

Every example should be covered by an automated test or by a recorded fixture
verification. Release notes and version baselines should link to the affected
guide rather than duplicating the full instructions.
