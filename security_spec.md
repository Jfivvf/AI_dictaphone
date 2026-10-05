# Security Specification (`security_spec.md`)

## 1. Data Invariants

1. **Identity Isolation (`UserProfile` & `UserPrivateInfo`)**:
   - A user document `/users/{userId}` can only be read, created, updated, or deleted by the authenticated, email-verified user whose `request.auth.uid == userId` and `data.uid == userId`.
   - User PII (`email`) is strictly isolated in `/users/{userId}/private/{infoId}`, which also verifies parent `/users/{userId}` existence and ownership via `get()`.
2. **Relational Ownership (`LectureDoc`)**:
   - A lecture `/users/{userId}/lectures/{lectureId}` cannot exist unless the parent `/users/{userId}` document exists and its `uid == request.auth.uid`.
   - `lecture.ownerId` must equal `request.auth.uid` and `userId`, and `lecture.id` must equal `lectureId`.
   - `ownerId`, `id`, and `createdAt` are immutable after creation.
3. **Sub-Resource Relational Sync (`TaskDoc`)**:
   - A task `/users/{userId}/lectures/{lectureId}/tasks/{taskId}` cannot exist without a valid parent lecture `/users/{userId}/lectures/{lectureId}` whose `ownerId == request.auth.uid`.
   - `task.ownerId == request.auth.uid`, `task.lectureId == lectureId`, and `task.id == taskId`.
4. **Strict Key & Volumetric Boundaries**:
   - Every write operation enforces exact key allowlists (`hasAll` and `hasOnly`) and strict `.size()` limits on strings and bounded arrays (`tags.size() <= 10`, `formulasLatex.size() <= 20`).
5. **Temporal Integrity**:
   - `createdAt` must equal `request.time` on `create` and remain immutable on `update`.
   - `updatedAt` must equal `request.time` on both `create` and `update`.

---

## 2. The "Dirty Dozen" Payloads

1. **Payload 1 (Identity Spoofing on Profile Creation)**:
   - Path: `/users/victim_uid` (Auth: `attacker_uid`)
   - Payload: `{"uid": "victim_uid", "name": "Attacker", "university": "MSU", "faculty": "Math", "group": "101", "semester": 1, "degree": "Bachelor", "theme": "dark", "createdAt": "SERVER_TIMESTAMP", "updatedAt": "SERVER_TIMESTAMP"}`
   - Expected: `PERMISSION_DENIED`
2. **Payload 2 (Shadow Field Injection on Profile Update)**:
   - Path: `/users/user_1` (Auth: `user_1`)
   - Payload: `{"uid": "user_1", "name": "Alex", "university": "MSU", "faculty": "Math", "group": "101", "semester": 1, "degree": "Bachelor", "theme": "dark", "isAdmin": true, "createdAt": "EXISTING", "updatedAt": "SERVER_TIMESTAMP"}`
   - Expected: `PERMISSION_DENIED`
3. **Payload 3 (Unverified Email Write Attempt)**:
   - Path: `/users/unverified_uid` (Auth: `unverified_uid`, `email_verified: false`)
   - Payload: `{"uid": "unverified_uid", "name": "Alex", "university": "MSU", "faculty": "Math", "group": "101", "semester": 1, "degree": "Bachelor", "theme": "dark", "createdAt": "SERVER_TIMESTAMP", "updatedAt": "SERVER_TIMESTAMP"}`
   - Expected: `PERMISSION_DENIED`
4. **Payload 4 (Cross-User PII Leak Read)**:
   - Path: `/users/victim_uid/private/info` (Auth: `attacker_uid`)
   - Operation: `get`
   - Expected: `PERMISSION_DENIED`
5. **Payload 5 (Orphaned Lecture Creation Without Parent User Document)**:
   - Path: `/users/no_profile_uid/lectures/lec_1` (Auth: `no_profile_uid`, `/users/no_profile_uid` does not exist)
   - Payload: Valid LectureDoc payload
   - Expected: `PERMISSION_DENIED`
6. **Payload 6 (Lecture OwnerId Mutation on Update)**:
   - Path: `/users/user_1/lectures/lec_1` (Auth: `user_1`)
   - Payload: Changing `ownerId` from `"user_1"` to `"user_2"`
   - Expected: `PERMISSION_DENIED`
7. **Payload 7 (Denial-of-Wallet Oversized String in Lecture Title)**:
   - Path: `/users/user_1/lectures/lec_1` (Auth: `user_1`)
   - Payload: `title` with 5,000 characters (exceeds maxLength 300)
   - Expected: `PERMISSION_DENIED`
8. **Payload 8 (Unbounded Array Overflow on Lecture Tags)**:
   - Path: `/users/user_1/lectures/lec_1` (Auth: `user_1`)
   - Payload: `tags` array with 25 elements (exceeds max 10)
   - Expected: `PERMISSION_DENIED`
9. **Payload 9 (Invalid Enum Value on Task Priority)**:
   - Path: `/users/user_1/lectures/lec_1/tasks/task_1` (Auth: `user_1`)
   - Payload: `priority: "critical"` (not in `['high', 'medium', 'low']`)
   - Expected: `PERMISSION_DENIED`
10. **Payload 10 (Orphaned Task Creation Without Parent Lecture)**:
    - Path: `/users/user_1/lectures/nonexistent_lec/tasks/task_1` (Auth: `user_1`)
    - Payload: Valid TaskDoc payload
    - Expected: `PERMISSION_DENIED`
11. **Payload 11 (Forged Client Timestamp on Lecture Creation)**:
    - Path: `/users/user_1/lectures/lec_1` (Auth: `user_1`)
    - Payload: `createdAt` set to past timestamp `2020-01-01T00:00:00Z` instead of `request.time`
    - Expected: `PERMISSION_DENIED`
12. **Payload 12 (Unauthorized Cross-User Lecture List Scraping)**:
    - Path: `/users/victim_uid/lectures` (Auth: `attacker_uid`)
    - Operation: `list` without matching `ownerId == request.auth.uid`
    - Expected: `PERMISSION_DENIED`

---

## 3. Test Runner

See `firestore.rules.test.ts` for the complete verification suite testing all 12 payloads.
