package com.example.mobile.ui.axiom

import android.Manifest
import android.content.Intent
import android.graphics.BitmapFactory
import android.media.MediaRecorder
import android.net.Uri
import android.provider.Settings
import android.widget.ImageView
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.example.mobile.network.StudyBuddyApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.io.File
import java.net.URLEncoder
import java.net.URL
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun NativeWorkspaceScreen(
    colors: AxiomColors,
    backend: MobileData,
    apiBaseUrl: String,
    onSaveConnection: (String) -> Unit,
    onSetDyslexic: (Boolean) -> Unit,
    onRefreshCore: () -> Unit,
) {
    var selected by remember { mutableStateOf<NativeFeature?>(null) }
    val api = remember(apiBaseUrl) { StudyBuddyApi(apiBaseUrl) }

    if (selected == null) {
        NativeScroll {
            Text("Native workspace", style = titleStyle(colors))
            Text("Every tool below is implemented in Kotlin and communicates directly with FastAPI.", color = colors.dim, fontSize = 12.sp)
            Text(
                if (backend.stats != null) "BACKEND · CONNECTED" else "BACKEND · ${if (backend.loading) "CHECKING…" else "UNREACHABLE"}",
                style = monoLabel(9, if (backend.stats != null) colors.accent else colors.dim, 0.1f),
            )
            nativeFeatures.forEach { feature ->
                NativeCard(colors, onClick = { selected = feature }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(feature.label, color = colors.text, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                            Text(feature.description, color = colors.dim, fontSize = 11.sp)
                        }
                        Text("›", style = monoLabel(18, colors.accent, 0f))
                    }
                }
            }
        }
        return
    }

    val feature = selected ?: return
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().background(colors.panel).border(1.dp, colors.line).padding(11.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("‹ ALL", style = monoLabel(10, colors.accent, 0.12f), modifier = Modifier.axClick { selected = null })
            Text(feature.label, color = colors.text, fontWeight = FontWeight.Medium)
        }
        when (feature.key) {
            "files" -> FilesNative(colors, api, onRefreshCore)
            "notes" -> NotesManagerNative(colors, api, onRefreshCore)
            "ask" -> AskNative(colors, api)
            "handwriting" -> HandwritingNative(colors, api, onRefreshCore)
            "video" -> VideoNative(colors, api, onRefreshCore)
            "flashcards" -> FlashcardsNative(colors, api, onRefreshCore)
            "audiobooks" -> AudiobooksNative(colors, api)
            "tasks" -> TasksNative(colors, api, onRefreshCore)
            "calendar" -> CalendarNative(colors, api)
            "settings" -> SettingsNative(colors, backend, api, apiBaseUrl, onSaveConnection, onSetDyslexic, onRefreshCore)
        }
    }
}

@Composable
private fun ConnectionPanel(
    colors: AxiomColors,
    backend: MobileData,
    apiBaseUrl: String,
    onSave: (String) -> Unit,
) {
    var input by remember(apiBaseUrl) { mutableStateOf(apiBaseUrl) }
    NativeCard(colors, accent = true) {
        Text("LAPTOP BACKEND", style = monoLabel(10, colors.accent, 0.14f))
        NativeField(colors, input, "http://192.168.1.20:8010") { input = it }
        NativeButton(colors, "SAVE & CONNECT") { if (input.isNotBlank()) onSave(input) }
        val state = when {
            backend.loading -> "CHECKING…" to colors.dim
            backend.error != null -> "UNREACHABLE" to Color(0xFFF87171)
            backend.stats != null -> "CONNECTED" to colors.accent
            else -> "UNREACHABLE" to Color(0xFFF87171)
        }
        Text("BACKEND · ${state.first}", style = monoLabel(9, state.second, 0.1f))
        backend.error?.let { Text(it, color = state.second, fontSize = 10.sp) }
    }
}

@Composable
private fun FilesNative(colors: AxiomColors, api: StudyBuddyApi, refreshCore: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var items by remember { mutableStateOf<JSONArray?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    suspend fun load() { items = api.arrayRequest("/api/items").value }
    LaunchedEffect(reload) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) scope.launch {
            runAction({ api.multipart(context, "/api/upload", "files", uris, mapOf("text" to text)); text = ""; load(); refreshCore() }, { message = it })
        }
    }
    NativeScroll {
        Text("Capture material", style = titleStyle(colors))
        NativeButton(colors, "CHOOSE FILES") { picker.launch(arrayOf("*/*")) }
        Text("Supports documents, audio, video, images, and text.", color = colors.dim, fontSize = 11.sp)
        NativeField(colors, text, "Paste or type study material…", minLines = 5) { text = it }
        NativeButton(colors, "SAVE TEXT", enabled = text.isNotBlank()) {
            scope.launch { runAction({ api.multipart(context, "/api/upload", "files", emptyList(), mapOf("text" to text)); text = ""; load(); refreshCore() }, { message = it }) }
        }
        NativeRecorder(colors, "RECORD LECTURE") { bytes ->
            api.multipartBytes("/api/upload", "files", "lecture-${System.currentTimeMillis()}.m4a", "audio/mp4", bytes, mapOf("text" to ""))
            load(); refreshCore()
            "Lecture uploaded for processing."
        }
        StatusText(colors, message)
        Text("Materials", style = sectionStyle(colors))
        items?.objects()?.forEach { item ->
            NativeCard(colors) {
                Text(item.optString("title").ifBlank { item.optString("filename") }, color = colors.text, fontSize = 13.sp)
                Text("${item.optString("kind")} · ${item.optString("status")}", style = monoLabel(9, colors.dim, 0.08f))
                item.optString("error").takeIf { it.isNotBlank() }?.let { error ->
                    Text(error, color = Color(0xFFF87171), fontSize = 10.sp)
                    NativeButton(colors, "RETRY") {
                        scope.launch { runAction({ api.objectRequest("/api/items/${item.getInt("id")}/retry", "POST", JSONObject()); load() }, { message = it }) }
                    }
                }
            }
        } ?: Text("Loading…", color = colors.dim)
    }
}

@Composable
private fun NotesManagerNative(colors: AxiomColors, api: StudyBuddyApi, refreshCore: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var notes by remember { mutableStateOf(JSONArray()) }
    var subjects by remember { mutableStateOf(JSONArray()) }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var edit by remember { mutableStateOf("") }
    var folder by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    suspend fun load() { notes = api.arrayRequest("/api/notes?limit=1000").value; subjects = api.arrayRequest("/api/subjects").value }
    LaunchedEffect(reload) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { scope.launch { runAction({ api.multipart(context, "/api/notes/import", "backup", listOf(it)); load(); refreshCore() }, { message = it }) } }
    }
    NativeScroll {
        Text("Notes manager", style = titleStyle(colors))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            NativeButton(colors, "IMPORT", Modifier.weight(1f)) { importer.launch(arrayOf("application/json")) }
            NativeButton(colors, "EXPORT", Modifier.weight(1f)) { openUrl(context, "${api.serverUrl}/api/notes/export") }
        }
        NativeField(colors, folder, "New subject folder") { folder = it }
        NativeButton(colors, "CREATE FOLDER", enabled = folder.isNotBlank()) {
            scope.launch { runAction({ api.objectRequest("/api/subjects", "POST", JSONObject().put("name", folder)); folder = ""; load() }, { message = it }) }
        }
        StatusText(colors, message)
        detail?.let { note ->
            NativeCard(colors, accent = true) {
                Text(note.optString("title").ifBlank { "Untitled" }, color = colors.text, fontWeight = FontWeight.Medium)
                note.optJSONArray("images")?.objects()?.forEach { image ->
                    RemoteImage("${api.serverUrl}${image.optString("url")}", 220)
                    image.optString("caption").takeIf { it.isNotBlank() }?.let {
                        Text(it, color = colors.dim, fontSize = 10.sp)
                    }
                }
                NativeField(colors, edit, "Markdown", minLines = 10) { edit = it }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NativeButton(colors, "SAVE", Modifier.weight(1f), edit.isNotBlank()) {
                        scope.launch { runAction({ api.objectRequest("/api/notes/${note.getInt("id")}", "PUT", JSONObject().put("markdown", edit)); load(); refreshCore() }, { message = it }) }
                    }
                    NativeButton(colors, "DELETE", Modifier.weight(1f)) {
                        scope.launch { runAction({ api.objectRequest("/api/notes/${note.getInt("id")}", "DELETE"); detail = null; load(); refreshCore() }, { message = it }) }
                    }
                }
                subjects.objects().forEach { subject ->
                    Text(
                        "MOVE TO ${subject.optString("name").uppercase()}",
                        style = monoLabel(9, colors.accent, 0.08f),
                        modifier = Modifier.axClick {
                            scope.launch { runAction({ api.objectRequest("/api/notes/${note.getInt("id")}", "PATCH", JSONObject().put("subject_id", subject.getInt("id"))); detail = null; load(); refreshCore() }, { message = it }) }
                        }.padding(vertical = 4.dp),
                    )
                }
            }
        }
        notes.objects().forEach { note ->
            NativeCard(colors, onClick = {
                scope.launch { runAction({
                    detail = api.objectRequest("/api/notes/${note.getInt("id")}").value
                    edit = detail?.optString("markdown").orEmpty()
                }, { message = it }) }
            }) {
                Text(note.optString("title").ifBlank { "Untitled" }, color = colors.text, fontSize = 13.sp)
                Text(note.optString("preview"), color = colors.dim, fontSize = 11.sp, maxLines = 2)
                Text(note.optString("subject").ifBlank { "UNFILED" }, style = monoLabel(9, colors.faint, 0.08f))
            }
        }
    }
}

@Composable
private fun AskNative(colors: AxiomColors, api: StudyBuddyApi) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var answer by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var history by remember { mutableStateOf(JSONArray()) }
    suspend fun loadHistory() { history = api.arrayRequest("/api/chat").value }
    LaunchedEffect(Unit) { runCatching { loadHistory() } }
    NativeScroll {
        Text("Ask your notes", style = titleStyle(colors))
        NativeField(colors, query, "Ask a cited question or create flashcards…", minLines = 3) { query = it }
        NativeButton(colors, "ASK", enabled = query.isNotBlank()) {
            scope.launch { runAction({ answer = api.objectRequest("/api/ask", "POST", JSONObject().put("question", query).put("subject", JSONObject.NULL)).value.optString("answer"); loadHistory() }, { message = it }) }
        }
        NativeRecorder(colors, "ASK WITH VOICE") { bytes ->
            val result = api.multipartBytes("/api/ask/audio", "audio", "question-${System.currentTimeMillis()}.m4a", "audio/mp4", bytes)
            answer = result.value.optString("answer"); loadHistory()
            "Transcribed: ${result.value.optString("transcript")}"
        }
        StatusText(colors, message)
        if (answer.isNotBlank()) NativeCard(colors, accent = true) { MarkdownText(answer, colors) }
        Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
            Text("History", style = sectionStyle(colors))
            Text("CLEAR", style = monoLabel(9, colors.accent, 0.1f), modifier = Modifier.axClick {
                scope.launch { runAction({ api.objectRequest("/api/chat", "DELETE"); loadHistory() }, { message = it }) }
            })
        }
        history.objects().takeLast(20).forEach { turn ->
            NativeCard(colors) {
                Text(turn.optString("role").uppercase(), style = monoLabel(9, colors.accent, 0.1f))
                Text(markdownAnnotated(turn.optString("content"), colors), color = colors.text, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun HandwritingNative(colors: AxiomColors, api: StudyBuddyApi, refreshCore: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pages by remember { mutableStateOf(JSONArray()) }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var message by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    suspend fun load() { pages = api.arrayRequest("/api/handwriting/pages").value }
    LaunchedEffect(reload) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    LaunchedEffect(detail?.optInt("id"), detail?.textOrEmpty("status")) {
        while (detail?.textOrEmpty("status") == "processing") {
            delay(2_000)
            val pageId = detail?.optInt("id") ?: break
            val result = runCatching { detail = api.objectRequest("/api/handwriting/pages/$pageId").value }
            if (result.isFailure) {
                message = result.exceptionOrNull()?.message.orEmpty()
                break
            }
        }
        load()
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) scope.launch { runAction({ val result = api.multipart(context, "/api/handwriting/upload", "files", uris); load(); result.value.optJSONArray("page_ids")?.optInt(0)?.takeIf { it > 0 }?.let { detail = api.objectRequest("/api/handwriting/pages/$it").value } }, { message = it }) }
    }
    NativeScroll {
        Text("Handwriting OCR", style = titleStyle(colors))
        NativeButton(colors, "UPLOAD PAGE PHOTOS") { picker.launch(arrayOf("image/*")) }
        StatusText(colors, message)
        detail?.let { page ->
            NativeCard(colors, accent = true) {
                Text(page.optString("filename"), color = colors.text, fontWeight = FontWeight.Medium)
                Text("STATUS · ${page.textOrEmpty("status").uppercase()}", style = monoLabel(9, colors.dim, 0.08f))
                page.textOrEmpty("error").takeIf { it.isNotBlank() }?.let {
                    Text(it, color = Color(0xFFF87171), fontSize = 10.sp)
                }
                page.optJSONArray("lines")?.objects()?.forEach { line ->
                    val detectedText = line.textOrEmpty("pred_text")
                    val savedCorrection = line.textOrEmpty("corrected_text")
                    var correction by remember(line.optInt("id"), savedCorrection, detectedText) {
                        mutableStateOf(savedCorrection.ifBlank { detectedText })
                    }
                    RemoteImage("${api.serverUrl}${line.optString("crop_url")}")
                    Text("DETECTED TEXT", style = monoLabel(9, colors.dim, 0.1f))
                    if (detectedText.isBlank()) {
                        Text("Waiting for LM Studio…", color = colors.dim, fontSize = 11.sp)
                    }
                    NativeField(colors, correction, "Correct recognized line") { correction = it }
                    NativeButton(colors, "SAVE LINE") {
                        scope.launch { runAction({ api.objectRequest("/api/handwriting/lines/${line.getInt("id")}", "PATCH", JSONObject().put("corrected_text", correction)); detail = api.objectRequest("/api/handwriting/pages/${page.getInt("id")}").value }, { message = it }) }
                    }
                }
                NativeButton(colors, "SEND TO NOTES") {
                    scope.launch { runAction({ api.objectRequest("/api/handwriting/pages/${page.getInt("id")}/to-notes", "POST", JSONObject()); refreshCore() }, { message = it }) }
                }
            }
        }
        pages.objects().forEach { page ->
            NativeCard(colors, onClick = { scope.launch { runAction({ detail = api.objectRequest("/api/handwriting/pages/${page.getInt("id")}").value }, { message = it }) } }) {
                Text(page.optString("filename"), color = colors.text, fontSize = 13.sp)
                Text("${page.optString("status")} · ${page.optInt("line_count")} lines", color = colors.dim, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun VideoNative(colors: AxiomColors, api: StudyBuddyApi, refreshCore: () -> Unit) {
    val scope = rememberCoroutineScope()
    var frames by remember { mutableStateOf(JSONArray()) }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var message by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    suspend fun load() { frames = api.arrayRequest("/api/video/frames").value }
    LaunchedEffect(reload) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    NativeScroll {
        Text("Video board review", style = titleStyle(colors))
        StatusText(colors, message)
        detail?.let { frame ->
            NativeCard(colors, accent = true) {
                Text(frame.optString("title").ifBlank { frame.optString("filename") }, color = colors.text, fontWeight = FontWeight.Medium)
                RemoteImage("${api.serverUrl}${frame.optString("image_url")}", 280)
                frame.optString("formatted_markdown").takeIf { it.isNotBlank() }?.let { MarkdownText(it, colors, fontSize = 11.sp, lineHeight = 17.sp) }
                NativeButton(colors, "RUN CROP OCR") {
                    scope.launch { runAction({ api.consumeEventStream("/api/video/frames/${frame.getInt("id")}/ocr-stream"); detail = api.objectRequest("/api/video/frames/${frame.getInt("id")}").value }, { message = it }) }
                }
                NativeButton(colors, "APPROVE & INDEX") {
                    scope.launch { runAction({ api.objectRequest("/api/video/frames/${frame.getInt("id")}/verify", "POST", JSONObject()); detail = null; load(); refreshCore() }, { message = it }) }
                }
                NativeButton(colors, "DELETE FRAME") {
                    scope.launch { runAction({ api.objectRequest("/api/video/frames/${frame.getInt("id")}", "DELETE"); detail = null; load() }, { message = it }) }
                }
            }
        }
        frames.objects().filter { it.optString("status") != "reviewed" }.forEach { frame ->
            NativeCard(colors, onClick = { scope.launch { runAction({ detail = api.objectRequest("/api/video/frames/${frame.getInt("id")}").value }, { message = it }) } }) {
                RemoteImage("${api.serverUrl}${frame.optString("image_url")}", 150)
                Text(frame.optString("title").ifBlank { frame.optString("filename") }, color = colors.text, fontSize = 13.sp)
                Text("@ ${formatSeconds(frame.optDouble("timestamp"))} · ${frame.optString("status")}", color = colors.dim, fontSize = 10.sp)
            }
        }
        if (frames.length() == 0) Text("No boards awaiting review.", color = colors.dim)
    }
}

@Composable
private fun FlashcardsNative(colors: AxiomColors, api: StudyBuddyApi, refreshCore: () -> Unit) {
    val scope = rememberCoroutineScope()
    var decks by remember { mutableStateOf(JSONArray()) }
    var deck by remember { mutableStateOf<JSONObject?>(null) }
    var index by remember { mutableIntStateOf(0) }
    var back by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    suspend fun load() { decks = api.arrayRequest("/api/flashcards").value }
    LaunchedEffect(Unit) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    NativeScroll {
        Text("Flashcard decks", style = titleStyle(colors))
        StatusText(colors, message)
        deck?.let { selected ->
            val cards = selected.optJSONArray("cards") ?: JSONArray()
            if (cards.length() > 0) {
                val card = cards.getJSONObject(index.coerceIn(0, cards.length() - 1))
                NativeCard(colors, accent = true, onClick = { back = !back }) {
                    Text(if (back) "ANSWER" else "QUESTION", style = monoLabel(9, colors.accent, 0.12f))
                    Spacer(Modifier.height(24.dp))
                    Text(markdownAnnotated(if (back) card.optString("back") else card.optString("front"), colors), color = colors.text, fontSize = 17.sp, lineHeight = 25.sp)
                    Text("Tap card to flip · ${index + 1}/${cards.length()}", color = colors.dim, fontSize = 10.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NativeButton(colors, "PREV", Modifier.weight(1f)) { index = (index - 1 + cards.length()) % cards.length(); back = false }
                        NativeButton(colors, "NEXT", Modifier.weight(1f)) { index = (index + 1) % cards.length(); back = false }
                    }
                    NativeButton(colors, "DELETE DECK") {
                        scope.launch { runAction({ api.objectRequest("/api/flashcards/${selected.getInt("id")}", "DELETE"); deck = null; load(); refreshCore() }, { message = it }) }
                    }
                }
            }
        }
        decks.objects().forEach { summary ->
            NativeCard(colors, onClick = { scope.launch { runAction({ deck = api.objectRequest("/api/flashcards/${summary.getInt("id")}").value; index = 0; back = false }, { message = it }) } }) {
                Text(summary.optString("title"), color = colors.text, fontSize = 13.sp)
                Text("${summary.optInt("card_count")} cards · ${summary.optString("subject")}", color = colors.dim, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun AudiobooksNative(colors: AxiomColors, api: StudyBuddyApi) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var notes by remember { mutableStateOf(JSONArray()) }
    var books by remember { mutableStateOf(JSONArray()) }
    var jobs by remember { mutableStateOf(JSONArray()) }
    var picked by remember { mutableStateOf(setOf<Int>()) }
    var message by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    suspend fun load() { notes = api.arrayRequest("/api/notes?limit=50").value; books = api.arrayRequest("/api/audiobooks").value; jobs = api.arrayRequest("/api/audiobooks/jobs").value }
    LaunchedEffect(reload) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    NativeScroll {
        Text("Audiobooks", style = titleStyle(colors))
        StatusText(colors, message)
        notes.objects().forEach { note ->
            val id = note.getInt("id")
            Text(
                "${if (id in picked) "☑" else "☐"} ${note.optString("title").ifBlank { "Untitled" }}",
                color = colors.text, fontSize = 13.sp,
                modifier = Modifier.axClick { picked = if (id in picked) picked - id else picked + id }.padding(vertical = 6.dp),
            )
        }
        NativeButton(colors, "GENERATE AUDIOBOOK", enabled = picked.isNotEmpty()) {
            scope.launch { runAction({
                val ids = JSONArray(); picked.forEach(ids::put)
                val name = notes.objects().firstOrNull { it.optInt("id") in picked }?.optString("title") ?: "audiobook"
                api.objectRequest("/api/audiobooks", "POST", JSONObject().put("note_ids", ids).put("name", name))
                picked = emptySet(); load()
            }, { message = it }) }
        }
        jobs.objects().filter { it.optString("status") != "done" }.forEach { job ->
            NativeCard(colors) { Text("${job.optString("name")} · ${job.optString("status")}", color = colors.text); job.optString("error").takeIf { it.isNotBlank() }?.let { Text(it, color = Color(0xFFF87171), fontSize = 10.sp) } }
        }
        books.objects().forEach { book ->
            NativeCard(colors, onClick = { openUrl(context, "${api.serverUrl}/api/audiobooks/${Uri.encode(book.optString("name"))}") }) {
                Text(book.optString("name").replace("_", " "), color = colors.text, fontSize = 13.sp)
                Text("${book.optDouble("size_mb")} MB · TAP TO PLAY/DOWNLOAD", style = monoLabel(9, colors.dim, 0.06f))
            }
        }
        NativeButton(colors, "REFRESH") { reload++ }
    }
}

@Composable
private fun TasksNative(colors: AxiomColors, api: StudyBuddyApi, refreshCore: () -> Unit) {
    val scope = rememberCoroutineScope()
    var tasks by remember { mutableStateOf(JSONArray()) }
    var label by remember { mutableStateOf("") }
    var due by remember { mutableStateOf("") }
    var calendar by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    suspend fun load() { tasks = api.arrayRequest("/api/tasks").value }
    LaunchedEffect(Unit) { runCatching { load() }.onFailure { message = it.message.orEmpty() } }
    NativeScroll {
        Text("Tasks", style = titleStyle(colors))
        NativeField(colors, label, "Task") { label = it }
        NativeField(colors, due, "Due date (optional)") { due = it }
        Text("${if (calendar) "☑" else "☐"} Add dated task to Google Calendar", color = colors.text, fontSize = 12.sp, modifier = Modifier.axClick { calendar = !calendar })
        NativeButton(colors, "ADD TASK", enabled = label.isNotBlank()) {
            scope.launch { runAction({
                api.objectRequest("/api/tasks", "POST", JSONObject().put("label", label).put("due", due.ifBlank { JSONObject.NULL }).put("add_to_calendar", calendar))
                label = ""; due = ""; calendar = false; load(); refreshCore()
            }, { message = it }) }
        }
        StatusText(colors, message)
        tasks.objects().forEach { task ->
            NativeCard(colors) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        if (task.optInt("done") != 0) "☑" else "☐",
                        color = colors.accent, fontSize = 18.sp,
                        modifier = Modifier.axClick {
                            scope.launch { runAction({ api.objectRequest("/api/tasks/${task.getInt("id")}", "PATCH", JSONObject().put("done", task.optInt("done") == 0)); load(); refreshCore() }, { message = it }) }
                        },
                    )
                    Column(Modifier.weight(1f).padding(horizontal = 10.dp)) {
                        Text(task.optString("label"), color = if (task.optInt("done") != 0) colors.dim else colors.text, textDecoration = if (task.optInt("done") != 0) TextDecoration.LineThrough else null)
                        task.optString("due").takeIf { it.isNotBlank() }?.let { Text(it, color = colors.dim, fontSize = 10.sp) }
                    }
                    Text("DELETE", style = monoLabel(8, Color(0xFFF87171), 0.06f), modifier = Modifier.axClick {
                        scope.launch { runAction({ api.objectRequest("/api/tasks/${task.getInt("id")}", "DELETE"); load(); refreshCore() }, { message = it }) }
                    })
                }
            }
        }
    }
}

@Composable
private fun CalendarNative(colors: AxiomColors, api: StudyBuddyApi) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf<JSONObject?>(null) }
    var proposals by remember { mutableStateOf(JSONArray()) }
    var events by remember { mutableStateOf(JSONArray()) }
    var message by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    var visibleMonth by remember { mutableStateOf(LocalDate.now().withDayOfMonth(1)) }
    var selectedDate by remember { mutableStateOf(LocalDate.now()) }
    suspend fun load() {
        status = api.objectRequest("/api/calendar/google/status").value
        proposals = api.arrayRequest("/api/calendar/proposals").value
        if (status?.optBoolean("connected") == true) {
            val zone = ZoneId.systemDefault()
            val start = visibleMonth.atStartOfDay(zone).toInstant().toString()
            val end = visibleMonth.plusMonths(1).atStartOfDay(zone).toInstant().toString()
            events = api.arrayRequest("/api/calendar/google/events?time_min=${enc(start)}&time_max=${enc(end)}").value
        } else events = JSONArray()
    }
    LaunchedEffect(reload, visibleMonth) {
        try {
            load()
            message = ""
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            // A restart (month change / resume refetch) is not an error.
            throw cancelled
        } catch (error: Exception) {
            message = error.message.orEmpty()
        }
    }
    // Refetch when the user comes back from the Google sign-in browser tab.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) reload++
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    NativeScroll {
        Text("Google Calendar", style = titleStyle(colors))
        val connected = status?.optBoolean("connected") == true
        Text(
            when {
                connected -> "CONNECTED"
                status == null -> "BACKEND OFFLINE · CALENDAR IN LOCAL MODE"
                status?.optBoolean("configured") == true -> "READY TO CONNECT"
                else -> "OAUTH NOT CONFIGURED"
            },
            style = monoLabel(10, if (connected) colors.accent else colors.dim, 0.1f),
        )
        if (!connected && status != null) {
            NativeButton(colors, "CONNECT") {
                scope.launch { runAction({ val url = api.objectRequest("/api/calendar/google/auth-url").value.getString("url"); openUrl(context, url) }, { message = it }) }
            }
            Text(
                "If Google sign-in cannot finish on the phone (the redirect goes to the laptop), connect once from the web app — the phone shares that connection automatically.",
                color = colors.dim, fontSize = 10.sp,
            )
        } else if (connected) {
            NativeButton(colors, "SYNC") { scope.launch { runAction({ api.objectRequest("/api/calendar/google/sync", "POST", JSONObject()); load() }, { message = it }) } }
            NativeButton(colors, "DISCONNECT") { scope.launch { runAction({ api.objectRequest("/api/calendar/google", "DELETE"); load() }, { message = it }) } }
        } else {
            Text(
                "The study-buddy server is unreachable, so Google events can't load. The month view below still works — reconnect and tap REFRESH to sync.",
                color = colors.dim, fontSize = 10.sp,
            )
        }
        StatusText(colors, message)
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            NativeButton(colors, "‹") {
                val target = visibleMonth.minusMonths(1)
                visibleMonth = target
                selectedDate = target
            }
            Text(
                visibleMonth.format(DateTimeFormatter.ofPattern("MMMM yyyy", Locale.getDefault())),
                color = colors.text,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
            )
            NativeButton(colors, "›") {
                val target = visibleMonth.plusMonths(1)
                visibleMonth = target
                selectedDate = target
            }
        }
        MonthGrid(
            colors = colors,
            month = visibleMonth,
            selectedDate = selectedDate,
            eventCounts = dayMarkers(emptyList(), events.objects().map { it.optString("start") }),
            onSelect = { date ->
                selectedDate = date
                if (date.month != visibleMonth.month || date.year != visibleMonth.year) {
                    visibleMonth = date.withDayOfMonth(1)
                }
            },
        )
        val selectedEvents = events.objects().filter { eventLocalDate(it.optString("start")) == selectedDate }
        Text(
            selectedDate.format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale.getDefault())),
            style = sectionStyle(colors),
        )
        if (selectedEvents.isEmpty()) {
            Text("No events on this day.", color = colors.dim, fontSize = 11.sp)
        }
        selectedEvents.forEach { event ->
            CalendarEventCard(colors, context, event)
        }
        Text("Date proposals", style = sectionStyle(colors))
        proposals.objects().forEach { proposal ->
            NativeCard(colors) {
                Text(proposal.optString("title"), color = colors.text, fontSize = 13.sp)
                Text("${proposal.optString("event_date")} ${proposal.optString("start_time")}", color = colors.dim, fontSize = 10.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NativeButton(colors, "APPROVE", Modifier.weight(1f)) { scope.launch { runAction({ api.objectRequest("/api/calendar/proposals/${proposal.getInt("id")}/approve", "POST", JSONObject()); load() }, { message = it }) } }
                    NativeButton(colors, "DISMISS", Modifier.weight(1f)) { scope.launch { runAction({ api.objectRequest("/api/calendar/proposals/${proposal.getInt("id")}/dismiss", "POST", JSONObject()); load() }, { message = it }) } }
                }
            }
        }
        NativeButton(colors, "REFRESH") { reload++ }
    }
}

/**
 * Month view shared by the Calendar tool and the Plan tab. Callers supply the
 * per-day marker counts so this stays agnostic about whether a dot is a Google
 * event, a task due date, or both.
 */
@Composable
internal fun MonthGrid(
    colors: AxiomColors,
    month: LocalDate,
    selectedDate: LocalDate,
    eventCounts: Map<LocalDate, Int>,
    onSelect: (LocalDate) -> Unit,
) {
    val firstVisibleDate = month.minusDays((month.dayOfWeek.value % 7).toLong())
    val cells = List(42) { firstVisibleDate.plusDays(it.toLong()) }
    // Own column: keeps week rows contiguous instead of inheriting the scroll column's item spacing.
    Column(Modifier.fillMaxWidth()) {
    Row(Modifier.fillMaxWidth()) {
        listOf("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT").forEach {
            Text(
                it,
                modifier = Modifier.weight(1f).padding(vertical = 7.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                style = monoLabel(8, colors.dim, 0.04f),
            )
        }
    }
    cells.chunked(7).forEach { week ->
        Row(Modifier.fillMaxWidth()) {
            week.forEach { date ->

                val selected = date == selectedDate
                val today = date == LocalDate.now()
                val inMonth = date.month == month.month && date.year == month.year
                Column(
                    Modifier.weight(1f).height(54.dp)
                        .border(0.5.dp, if (selected) colors.accent else colors.line)
                        .background(
                            when {
                                selected -> colors.accent.copy(alpha = 0.16f)
                                today -> colors.accent.copy(alpha = 0.06f)
                                else -> Color.Transparent
                            }
                        )
                        .axClick { onSelect(date) }
                        .padding(top = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box(
                        Modifier.size(25.dp)
                            .background(if (today) colors.accent else Color.Transparent),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            date.dayOfMonth.toString(),
                            color = when {
                                today -> colors.bg
                                selected -> colors.accent
                                inMonth -> colors.text
                                else -> colors.faint
                            },
                            fontSize = 11.sp,
                            fontWeight = if (today || selected) FontWeight.Bold else FontWeight.Normal,
                        )
                    }
                    eventCounts[date]?.let { count ->
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            repeat(count.coerceAtMost(3)) {
                                Box(Modifier.size(3.dp).background(colors.accent))
                            }
                        }
                    }
                }
            }
        }
    }
    }
}

@Composable
internal fun CalendarEventCard(colors: AxiomColors, context: android.content.Context, event: JSONObject) {
    NativeCard(colors) {
        Text(event.optString("summary").ifBlank { "Untitled event" }, color = colors.text, fontSize = 13.sp)
        Text(if (event.optBoolean("all_day")) "All day" else formatEventTime(event.optString("start"), event.optString("end")), color = colors.dim, fontSize = 10.sp)
        event.optString("location").takeIf { it.isNotBlank() }?.let { Text(it, color = colors.dim, fontSize = 10.sp) }
        event.optString("description").takeIf { it.isNotBlank() }?.let { Text(it, color = colors.dim, fontSize = 11.sp) }
        event.optString("html_link").takeIf { it.isNotBlank() }?.let { link ->
            Text("OPEN IN GOOGLE", style = monoLabel(9, colors.accent, 0.08f), modifier = Modifier.axClick { openUrl(context, link) })
        }
    }
}

@Composable
private fun SettingsNative(
    colors: AxiomColors,
    backend: MobileData,
    api: StudyBuddyApi,
    apiBaseUrl: String,
    onSave: (String) -> Unit,
    onSetDyslexic: (Boolean) -> Unit,
    refreshCore: () -> Unit,
) {
    var health by remember { mutableStateOf<JSONObject?>(null) }
    var message by remember { mutableStateOf("") }
    LaunchedEffect(apiBaseUrl) { runCatching { health = api.objectRequest("/api/health").value }.onFailure { message = it.message.orEmpty() } }
    NativeScroll {
        Text("System & connection", style = titleStyle(colors))
        ConnectionPanel(colors, backend, apiBaseUrl, onSave)
        NativeCard(colors) {
            Text("STUDY BUDDY API", style = monoLabel(10, colors.accent, 0.12f))
            listOf("ok", "version", "llm", "storage", "vector_index").forEach { key ->
                Text("${key.replace("_", " ").uppercase()} · ${health?.opt(key) ?: "checking"}", color = colors.text, fontSize = 12.sp)
            }
        }
        backend.stats?.let { stats ->
            NativeCard(colors) {
                Text("LIVE STORAGE", style = monoLabel(10, colors.accent, 0.12f))
                Text("${stats.notes} notes · ${stats.files} materials · ${stats.chunks} chunks", color = colors.text, fontSize = 12.sp)
                Text("${stats.flashcards} flashcards · ${stats.audiobooks} audiobooks", color = colors.text, fontSize = 12.sp)
                Text("${stats.diskUsedGb} / ${stats.diskTotalGb} GB disk used", color = colors.dim, fontSize = 11.sp)
            }
        }
        ReadingPanel(colors, onSetDyslexic)
        StatusText(colors, message)
        NativeButton(colors, "REFRESH EVERYTHING") { refreshCore() }
    }
}

/** Dyslexia-friendly reading toggle — mirrors the web app's Reading setting. */
@Composable
private fun ReadingPanel(colors: AxiomColors, onSetDyslexic: (Boolean) -> Unit) {
    val on = LocalDyslexicReading.current
    NativeCard(colors) {
        Text("READING", style = monoLabel(10, colors.accent, 0.12f))
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text("Dyslexia-friendly reading", style = sectionStyle(colors))
                Text(
                    "OpenDyslexic typeface with wider letter spacing and taller lines",
                    color = colors.dim,
                    fontSize = 11.sp,
                    lineHeight = 16.sp,
                )
            }
            AxSwitch(colors, on, onSetDyslexic)
        }
    }
}

@Composable
private fun AxSwitch(colors: AxiomColors, on: Boolean, onChange: (Boolean) -> Unit) {
    val knobOffset by animateDpAsState(if (on) 20.dp else 2.dp, label = "knob")
    Box(
        Modifier
            .size(width = 42.dp, height = 24.dp)
            .border(1.dp, if (on) colors.accent else colors.line2)
            .axClick { onChange(!on) },
    ) {
        Box(
            Modifier
                .offset(x = knobOffset, y = 4.dp)
                .size(16.dp)
                .background(if (on) colors.accent else colors.dim)
        )
    }
}

@Composable
private fun NativeRecorder(
    colors: AxiomColors,
    label: String,
    onRecorded: suspend (ByteArray) -> String,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var recorder by remember { mutableStateOf<MediaRecorder?>(null) }
    var file by remember { mutableStateOf<File?>(null) }
    var recording by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    fun start() {
        val output = File(context.cacheDir, "study-buddy-${System.currentTimeMillis()}.m4a")
        runCatching {
            MediaRecorder(context).apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioEncodingBitRate(128_000)
                setAudioSamplingRate(44_100)
                setOutputFile(output.absolutePath)
                prepare(); start()
            }
        }.onSuccess { recorder = it; file = output; recording = true; message = "Recording…" }
            .onFailure { message = it.message ?: "Could not start microphone" }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) start() else message = "Microphone permission denied."
    }
    DisposableEffect(Unit) { onDispose { runCatching { recorder?.stop() }; recorder?.release() } }
    NativeButton(colors, if (recording) "STOP & UPLOAD" else label) {
        if (!recording) permission.launch(Manifest.permission.RECORD_AUDIO)
        else {
            runCatching { recorder?.stop() }
            recorder?.release(); recorder = null; recording = false
            file?.let { captured ->
                scope.launch {
                    runAction({ message = onRecorded(withContext(Dispatchers.IO) { captured.readBytes() }); captured.delete() }, { message = it })
                }
            }
        }
    }
    StatusText(colors, message)
}

@Composable
internal fun RemoteImage(url: String, height: Int = 100) {
    var bytes by remember(url) { mutableStateOf<ByteArray?>(null) }
    LaunchedEffect(url) { bytes = withContext(Dispatchers.IO) { runCatching { URL(url).readBytes() }.getOrNull() } }
    AndroidView(
        modifier = Modifier.fillMaxWidth().height(height.dp).background(Color.Black.copy(alpha = 0.1f)),
        factory = { ImageView(it).apply { scaleType = ImageView.ScaleType.FIT_CENTER } },
        update = { view -> bytes?.let { view.setImageBitmap(BitmapFactory.decodeByteArray(it, 0, it.size)) } },
    )
}

@Composable
private fun NativeScroll(content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) =
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        content = content,
    )

@Composable
private fun NativeCard(
    colors: AxiomColors,
    accent: Boolean = false,
    onClick: (() -> Unit)? = null,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth().border(1.dp, if (accent) colors.accent else colors.line).background(colors.panel)
            .let { if (onClick != null) it.axClick(onClick) else it }.padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(9.dp),
        content = content,
    )
}

@Composable
private fun NativeField(
    colors: AxiomColors,
    value: String,
    placeholder: String,
    minLines: Int = 1,
    onValueChange: (String) -> Unit,
) {
    Box(Modifier.fillMaxWidth().border(1.dp, colors.line2).background(colors.panel2).padding(11.dp)) {
        if (value.isBlank()) Text(placeholder, color = colors.faint, fontSize = 12.sp)
        BasicTextField(
            value, onValueChange,
            modifier = Modifier.fillMaxWidth().heightIn(min = (20 * minLines).dp),
            textStyle = TextStyle(fontFamily = Sans, fontSize = 12.sp, lineHeight = 18.sp, color = colors.text),
            cursorBrush = SolidColor(colors.accent),
            minLines = minLines,
        )
    }
}

@Composable
private fun NativeButton(
    colors: AxiomColors,
    label: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Box(
        modifier.then(Modifier.border(1.dp, if (enabled) colors.accent else colors.line2)
            .let { if (enabled) it.axClick(onClick) else it }.padding(horizontal = 12.dp, vertical = 10.dp)),
        contentAlignment = Alignment.Center,
    ) { Text(label, style = monoLabel(9, if (enabled) colors.accent else colors.faint, 0.12f)) }
}

@Composable private fun StatusText(colors: AxiomColors, text: String) {
    if (text.isNotBlank()) Text(text, color = if (text.contains("fail", true) || text.contains("error", true) || text.contains("cannot", true)) Color(0xFFF87171) else colors.dim, fontSize = 10.sp)
}
@Composable private fun titleStyle(colors: AxiomColors) = TextStyle(fontFamily = Sans, fontSize = 22.sp, fontWeight = FontWeight.Medium, color = colors.text)
@Composable private fun sectionStyle(colors: AxiomColors) = TextStyle(fontFamily = Sans, fontSize = 15.sp, fontWeight = FontWeight.Medium, color = colors.text)
internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
private fun JSONObject.textOrEmpty(name: String): String =
    if (!has(name) || isNull(name)) "" else optString(name)
private fun formatSeconds(value: Double) =
    if (value.isNaN()) "0:00"
    else "${(value / 60).toInt()}:${(value.toInt() % 60).toString().padStart(2, '0')}"
internal fun enc(value: String) = URLEncoder.encode(value, Charsets.UTF_8.name())

/** Google events carry either a plain date or an offset date-time; map both to the device's local day. */
private fun formatEventTime(start: String, end: String): String = runCatching {
    val zone = ZoneId.systemDefault()
    val startAt = OffsetDateTime.parse(start).atZoneSameInstant(zone)
    val dayFmt = DateTimeFormatter.ofPattern("EEE, d MMM", Locale.getDefault())
    val timeFmt = DateTimeFormatter.ofPattern("H:mm")
    val endAt = runCatching { OffsetDateTime.parse(end).atZoneSameInstant(zone) }.getOrNull()
    buildString {
        append(startAt.format(dayFmt))
        append(" · ")
        append(startAt.format(timeFmt))
        if (endAt != null) {
            append(" – ")
            append(endAt.format(timeFmt))
        }
    }
}.getOrDefault(start)

private fun openUrl(context: android.content.Context, url: String) {
    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
}
private suspend fun runAction(block: suspend () -> Unit, onError: (String) -> Unit) {
    runCatching { block() }.onFailure { onError(it.message ?: "Request failed") }
}
