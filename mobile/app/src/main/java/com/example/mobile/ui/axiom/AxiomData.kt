package com.example.mobile.ui.axiom

enum class AxiomScreen(val label: String) {
    Home("HOME"), Notes("NOTES"), Cards("CARDS"), Plan("PLAN"), All("ALL")
}

data class NativeFeature(val label: String, val description: String, val key: String)

val nativeFeatures = listOf(
    NativeFeature("Files & capture", "Upload material, paste text, or record a lecture", "files"),
    NativeFeature("Notes manager", "Read, edit, move, import, export, and delete notes", "notes"),
    NativeFeature("Ask & voice", "Ask cited questions or record a voice question", "ask"),
    NativeFeature("Handwriting", "Upload pages, correct OCR, and create notes", "handwriting"),
    NativeFeature("Video boards", "Review lecture frames, run OCR, approve, or delete", "video"),
    NativeFeature("Flashcards", "Study and manage every generated deck", "flashcards"),
    NativeFeature("Audiobooks", "Generate and open narrated notes", "audiobooks"),
    NativeFeature("Tasks", "Create, complete, schedule, and delete tasks", "tasks"),
    NativeFeature("Calendar", "Connect, sync, and approve Google Calendar proposals", "calendar"),
    NativeFeature("System", "Live backend health, storage, and connection settings", "settings"),
)

data class BackendStats(
    val notes: Int,
    val files: Int,
    val chunks: Int,
    val flashcards: Int,
    val audiobooks: Int,
    val diskUsedGb: Double,
    val diskTotalGb: Double,
)

data class BackendNote(
    val id: Int,
    val itemId: Int,
    val title: String?,
    val preview: String,
    val subject: String?,
    val createdAt: Long,
)

data class BackendTask(
    val id: Int,
    val label: String,
    val due: String?,
    val done: Boolean,
    val createdAt: Long,
)

data class FlashcardDeckSummary(
    val id: Int,
    val title: String,
    val topic: String,
    val subject: String?,
    val cardCount: Int,
)

data class BackendFlashcard(
    val id: Int,
    val front: String,
    val back: String,
    val position: Int,
)

data class FlashcardDeck(
    val id: Int,
    val title: String,
    val topic: String,
    val subject: String?,
    val cards: List<BackendFlashcard>,
)

data class AskResponse(val answer: String)

data class MobileData(
    val stats: BackendStats? = null,
    val notes: List<BackendNote> = emptyList(),
    val tasks: List<BackendTask> = emptyList(),
    val decks: List<FlashcardDeckSummary> = emptyList(),
    val selectedDeck: FlashcardDeck? = null,
    val loading: Boolean = true,
    val error: String? = null,
    val lastRequestId: String? = null,
)
