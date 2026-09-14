# ARL Moderator Guided Workflow Patch

This patch changes only `static/moderator.html`.

## Added
- Persistent 8-step operator checklist at the top of the moderator page.
- Recommended next action and progress count.
- Automatic completion indicators where ARL can detect status.
- Manual checks for LabRecorder recording, camera/microphone verification, and selected stream verification.
- Manual checklist state is stored in the browser using localStorage.
- Separate visual treatment for recording/testing tools.

## Development behavior
- No phase or experiment buttons are locked.
- All existing moderator controls remain available for direct testing.
- Experiment controller and backend logic are unchanged.

## Install
Copy `static/moderator.html` into the active Git repository and replace the existing file.
