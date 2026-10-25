---
description: Copy a lesson's finished modules in from the course repo's solution folder when you're behind
argument-hint: "<lesson number to catch up on, e.g. 02>"
---
<task>Catch me up on lesson $ARGUMENTS with the finished code.</task>

<steps>
1. Ask me where my copy of the course repo is (the folder I cloned), unless I've said.
   The finished code is in `<course repo>/solution/lesson-$ARGUMENTS/`.
2. Read lessons/$ARGUMENTS-*/SPEC.md, the "You build" list, for the modules of lesson
   $ARGUMENTS.
3. Show me which of my files would be replaced, and wait for my yes.
4. Copy those files from the solution folder into this folder, then run /verify.
</steps>

<note>If this folder is a git repo, suggest I commit my own attempt first, so I can
compare it with the finished version afterwards (`git diff`).</note>
