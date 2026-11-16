# WhaleMai Next maintenance

Read README.md and docs/MAINTENANCE.md before changing this app. Commit changes to the application or upstream-overlay. WhaleGirl and MaiBot are regenerated from fixed source archives. When making an experimental change to the generated WhaleGirl checkout, propagate only reviewed source files to the overlay.

Keep instance data out of release artifacts. Use only synthetic chat data in automated tests. Keep account checks, whitelist, cancellation, draft checks and the single-attempt contract at the final send boundary. Do not enable process-memory writes or automatic key recovery. Do not touch an existing WhaleGirl or MaiBot deployment. Live send testing requires explicit target and content authorization.
