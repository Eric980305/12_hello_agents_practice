# Design QA — 2026-08-06 authentication and ownership boundary

## Evidence

- User references: the desktop and mobile authentication screenshots supplied on 2026-08-06.
- Mobile login: `artifacts/ui/shared-login-mobile.png`
- Final mobile login: `artifacts/ui/shared-login-mobile-final.png`
- Final desktop login: `artifacts/ui/shared-login-desktop-final.png`
- Before/after mobile comparison: `artifacts/ui/shared-login-mobile-comparison.png`
- Authenticated desktop application: `artifacts/ui/shared-app-desktop-final.png`
- Authenticated mobile application: `artifacts/ui/shared-app-mobile-final2.png`
- Desktop knowledge-base manager: `artifacts/ui/shared-manager-desktop-final.png`
- Mobile knowledge-base manager: `artifacts/ui/shared-manager-mobile-final2.png`
- Current desktop login: `artifacts/ui/kb-fix-login-desktop.png`
- Current mobile login: `artifacts/ui/kb-fix-login-mobile.png`
- Current authenticated desktop application: `artifacts/ui/kb-fix-app-desktop.png`
- Current authenticated mobile application: `artifacts/ui/kb-fix-app-mobile.png`
- Current desktop knowledge-base manager: `artifacts/ui/kb-fix-manager-desktop.png`
- Current mobile knowledge-base manager: `artifacts/ui/kb-fix-manager-mobile.png`
- Current reference/implementation desktop comparison: `artifacts/ui/kb-fix-comparison.png`

## Verified behavior

- Login and registration are separate animated visual states. Registration accepts a six-character password, shows a success result, returns to login after success, and does not create a session automatically.
- The compact “没有账号？ 注册” action is aligned above the primary login action. Desktop uses one bounded card; mobile removes the outer border, shadow, and duplicate Gradio wrapper styling.
- The mobile login title “欢迎来到浚民的智能知识库” stays on one line. Username and password fields render as 48-pixel-high white controls with explicit borders and dark text in the light theme. Desktop and 390×844 live browser runs have no horizontal overflow, and all three authenticated primary destinations remain visible at mobile width.
- A real login initialized SQLite, Qdrant, and the application workspace. The selector exposed “所有知识库” and the user-visible shared library “共享知识库”; selecting it changed both the control value and the managed-library status. Its internal ID and namespace remained stable.
- Repeated clicks on the knowledge-base and file-type selectors changed `aria-expanded` from `true` back to `false`, proving that the menus close without selecting an item.
- The knowledge-base manager renders as a centered desktop dialog and a flat mobile sheet. Its close action is red with white text, and the shared-library selector is not clipped.
- The complete regression suite passed 113 tests, Python compilation passed, dependency validation reported no broken requirements, and the temporary QA account was deleted afterward.
- The current-session report path is covered by a regression test with real recorded turns from two knowledge bases. It requires two knowledge-base-labeled sections and excludes notes/documents as invented dialogue input.
- The corrected selector was verified with a real temporary account: a fresh account exposed `所有知识库` and `共享知识库`; after creating a personal library it exposed all three choices and selected the new concrete library. The aggregate view retained the personal document, while upload, retrieval, notes, and reporting stayed scoped to its concrete namespace.
- Reloading the authenticated page restored the same account and accessible library catalog. Desktop and 390×844 captures were taken after the fix, both mobile login and authenticated views reported `scrollWidth == clientWidth`, and the browser console reported no application errors during the exercised flow.
- Deleting the uploaded fixture removed its SQLite document/chunk rows and its namespace-filtered Qdrant vectors. The visual and functional QA account, knowledge base, fixture, report, and derived records were removed after verification.

## Intentional boundaries

- Authentication is local username/password authentication, not federated SSO. Internet deployment still requires server-side session cookies, CSRF protection, rate limiting, account recovery, and operational identity controls.
- All authenticated users can manage the shared knowledge base in this learning stage. Production multi-user deployment requires role-based shared-library write authorization.
- Existing personal knowledge bases remain owner-scoped and are not merged into the shared namespace.

final result: passed

## 2026-08-07 rounded mobile authentication card

- User reference: `df5bba5aba5608ed52936ff2f242c978.jpg`, showing the square-edged dark mobile login surface.
- Desktop implementation: `artifacts/ui/auth-rounded-desktop.png`.
- Mobile light implementation: `artifacts/ui/auth-rounded-mobile-light.png`.
- Mobile dark implementation: `artifacts/ui/auth-rounded-mobile-dark.png`.
- The implementation keeps one visual boundary: a 24 px authentication card. Inputs and the primary action use 14 px radii; inner Gradio wrappers stay transparent and borderless.
- At 390 × 844 the card is 366 px wide with 12 px side margins, the document width equals the viewport width, and no horizontal overflow is present. Dark-theme inputs render with an explicit `rgb(15, 23, 42)` surface, `rgb(100, 116, 139)` border, and `rgb(248, 250, 252)` text.
- At 1280 × 720 the same component remains a centered 520 px desktop card, so the mobile polish does not alter the desktop information hierarchy.

final result: passed

## 2026-08-07 document-list flow layout

- Reference: `截屏2026-08-07 11.02.15.png` supplied by the user.
- Root cause: Gradio 6.22 virtualizes Dataframe rows and could retain the previous list's measured canvas height after an asynchronous knowledge-base or search update. Changing only `row_count` did not invalidate that cached height.
- The document table now uses fixed, non-wrapping 44 px rows and CSS content queries to clamp lists of zero through seven rendered rows to their exact height. Longer lists keep Gradio's bounded scroll viewport.
- Live browser checks covered dynamic transitions between two, one, zero, and two rows. The body heights were respectively 88, 44, 0, and 88 px; the upload panel remained 13 px below the table in every state.
- Verified at 1440 px desktop and 390 × 844 mobile viewports. The page has no horizontal overflow (`scrollWidth == innerWidth`); the document table itself remains horizontally scrollable on narrow screens so columns are not silently discarded.

final result: passed
