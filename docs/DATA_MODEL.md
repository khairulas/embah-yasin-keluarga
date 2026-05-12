# Firestore Data Model — Sistem Embah Yasin

## Design principles

1. **Person-centric, not household-centric.** A person exists independently of a household. They can belong to multiple households (e.g., a married daughter is in her parents' household *and* her own).
2. **Denormalize for read efficiency.** Firestore charges per document read. We duplicate names into membership docs so household lists don't need N extra reads.
3. **Audit every write.** Each document has an `audit_log` sub-collection. We never delete — only mark `is_deleted: true`.
4. **Use deterministic IDs where possible** so re-imports don't create duplicates.

## Collections

### `/persons/{person_id}`

The atomic unit. One document per individual human.

```
{
  person_id: "p_khairul_anwar_bin_sedek",      // doc ID; generated from name
  full_name: "Khairul Anwar bin Sedek",
  jantina: "L",                                 // "L" | "P"
  tahun_lahir: 1973,                            // integer; null if unknown
  tarikh_lahir: "1973-05-15",                   // ISO date; null if unknown (more precise than tahun_lahir)
  status: "alive",                              // "alive" | "deceased" | "unknown"
  tarikh_meninggal: null,                       // ISO date if deceased
  notes: "",

  // Contact info (flat, since usually 1 of each)
  email: "khairulanwars@gmail.com",
  phone: "+60194746960",                        // E.164 format
  alt_phone: null,

  // Address
  address: {
    line1: "No 12, Jalan Mawar 3",
    line2: "Taman Bahagia",
    poskod: "05400",
    bandar: "Alor Setar",
    negeri: "Kedah",
    negara: "Malaysia"
  },

  // Family tree links (arrays of person_id)
  parent_ids: ["p_sedek_xxx", "p_mother_xxx"],
  spouse_ids: ["p_rozita_hamzah"],              // current and former; ordered by recency
  child_ids: ["p_nur_athirah", "p_amsyar_wafiq"],

  // Auth & ownership
  claimed_by_uid: "firebase_auth_uid_xxx",      // null if no one has claimed this profile yet
  claimed_at: <timestamp>,

  // Standard metadata
  created_at: <timestamp>,
  created_by_uid: "firebase_auth_uid_xxx",
  updated_at: <timestamp>,
  updated_by_uid: "firebase_auth_uid_xxx",
  is_deleted: false
}
```

**Sub-collection: `/persons/{person_id}/audit_log/{log_id}`**

```
{
  changed_at: <timestamp>,
  changed_by_uid: "firebase_auth_uid_xxx",
  changed_by_email: "user@example.com",
  changed_by_name: "Khairul Anwar",
  action: "update",                             // "create" | "update" | "delete" | "claim"
  fields_changed: ["address", "phone"],
  before: { address: {...}, phone: "..." },     // only fields that changed
  after:  { address: {...}, phone: "..." }
}
```

### `/households/{household_id}`

A registered family unit (one Google Form submission == one household, originally).

```
{
  household_id: "h_001",
  ketua_person_id: "p_khairul_anwar_bin_sedek",
  members: [                                    // denormalized for cheap list view
    { person_id: "p_khairul_anwar_bin_sedek", role: "ketua",    full_name_cached: "Khairul Anwar bin Sedek" },
    { person_id: "p_rozita_hamzah",           role: "pasangan", full_name_cached: "Rozita Hamzah" },
    { person_id: "p_nur_athirah",             role: "anak",     full_name_cached: "Nur Athirah binti Khairul Anwar" }
  ],
  registered_by_email: "khairulanwars@gmail.com",
  registered_at: <timestamp>,
  notes: "",
  created_at, created_by_uid, updated_at, updated_by_uid, is_deleted
}
```

Roles: `"ketua" | "pasangan" | "anak" | "ibu_bapa" | "lain"`

**Sub-collection: `/households/{household_id}/audit_log/{log_id}`** — same shape as person audit.

### `/users/{firebase_auth_uid}`

Maps a Firebase Auth user (Google account) to their person record.

```
{
  uid: "firebase_auth_uid_xxx",
  email: "khairulanwars@gmail.com",
  display_name: "Khairul Anwar",
  photo_url: "https://...",
  linked_person_id: "p_khairul_anwar_bin_sedek",   // null until they claim a profile
  role: "member",                                  // "member" | "admin"
  first_login_at: <timestamp>,
  last_login_at: <timestamp>
}
```

The `linked_person_id` is the bridge: once a user claims their profile, every write
they make is attributable to a specific Person, which is what makes the audit log
meaningful.

## Why this shape?

- **`person_ids` for relationships** lets us walk a family tree: from any person,
  follow `parent_ids` upward or `child_ids` downward. This is the *whole point* of a
  silsilah keluarga system.
- **Households as a separate concept from Persons** because relationships are not the
  same as cohabitation. A grandmother is in the family tree but lives alone.
- **Denormalized member names in households** avoid expensive joins on the household
  list page (where you only need names).
- **Audit sub-collections** rather than a global audit table because Firestore queries
  on sub-collections are efficient when you're already viewing the parent.
- **Soft delete (`is_deleted`)** because family data is sensitive and accidental
  deletes happen.

## Indexes needed

- `persons` where `is_deleted == false` order by `full_name` (for search)
- `households` where `is_deleted == false` order by `registered_at desc`
- `users` where `linked_person_id == <id>` (for "who has claimed this profile")
- Collection group query on `audit_log` order by `changed_at desc` (for global recent activity feed)
