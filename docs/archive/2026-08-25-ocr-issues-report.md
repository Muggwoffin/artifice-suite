# OCR issues — original bug report, 2026-08-25

> **Provenance.** The maintainer's own note, written in Obsidian and kept
> verbatim below. It is the origin document for
> [the Node/Electron shell assessment](../decisions/2026-08-25-node-shell-assessment.md),
> which investigated the question it asks at the end.
>
> **All four issues were fixed**, and none was a WebView problem — see that
> assessment's outcome table.
>
> Two things to know when reading it:
>
> - The `![[Pasted image …]]` lines are **Obsidian wikilinks**, and the
>   screenshots they point at are not in this repository. They showed the
>   save-settings error, the Tropy directory-permission message, and the
>   pipeline 404.
> - The Obsidian vault frontmatter (`type: writing_project`, `cssclasses`, and
>   a `created: 2026-07-27` that predates the note's actual date) has been
>   removed as app metadata with no meaning here. Nothing else was changed.

## OCR Issues
![[Pasted image 20260825114056.png]]

When I click save settings, I get an error Could not save settings telling me to permit endpoints outside my own network

![[Pasted image 20260825114201.png]]

When I try to import from tropy via browse project, I get a note saying that this server is not permitted to access the directory.

![[Pasted image 20260825114305.png]]

When I export a Tropy JSON file and add it to OCR, it loads the file folder successfully, but then when I run the pipeline I get a 404 error. In this case, Ollama and the OCR model were connected.

My question: is this all happening because of the WebView? Should we switch to a Node app? Even if that leads to maintainability issues down the line, we are constantly running into this error, and I think a Node app may be the solution. 