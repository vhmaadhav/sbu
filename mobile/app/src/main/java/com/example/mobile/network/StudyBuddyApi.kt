package com.example.mobile.network

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.example.mobile.BuildConfig
import com.example.mobile.ui.axiom.AskResponse
import com.example.mobile.ui.axiom.BackendFlashcard
import com.example.mobile.ui.axiom.BackendNote
import com.example.mobile.ui.axiom.BackendStats
import com.example.mobile.ui.axiom.BackendTask
import com.example.mobile.ui.axiom.FlashcardDeck
import com.example.mobile.ui.axiom.FlashcardDeckSummary
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.io.DataOutputStream
import java.util.UUID

class ApiException(
    val statusCode: Int,
    val requestId: String?,
    message: String,
) : Exception(message)

data class ApiResult<T>(val value: T, val requestId: String?)

class StudyBuddyApi(private val baseUrl: String = BuildConfig.API_BASE_URL) {
    val serverUrl: String get() = baseUrl
    suspend fun stats() = get("/api/stats") { json ->
        BackendStats(
            notes = json.int("notes"),
            files = json.int("files"),
            chunks = json.int("chunks"),
            flashcards = json.int("flashcards"),
            audiobooks = json.int("audiobooks"),
            diskUsedGb = json.double("disk_used_gb"),
            diskTotalGb = json.double("disk_total_gb"),
        )
    }

    suspend fun notes() = getArray("/api/notes?limit=200") { json ->
        BackendNote(
            id = json.int("id"),
            itemId = json.int("item_id"),
            title = json.stringOrNull("title"),
            preview = json.string("preview"),
            subject = json.stringOrNull("subject"),
            createdAt = json.long("created_at"),
        )
    }

    suspend fun tasks() = getArray("/api/tasks") { json ->
        BackendTask(
            id = json.int("id"),
            label = json.string("label"),
            due = json.stringOrNull("due"),
            done = json.int("done") != 0,
            createdAt = json.long("created_at"),
        )
    }

    suspend fun decks() = getArray("/api/flashcards") { json ->
        FlashcardDeckSummary(
            id = json.int("id"),
            title = json.string("title"),
            topic = json.string("topic"),
            subject = json.stringOrNull("subject"),
            cardCount = json.int("card_count"),
        )
    }

    suspend fun deck(id: Int) = get("/api/flashcards/$id") { json ->
        FlashcardDeck(
            id = json.int("id"),
            title = json.string("title"),
            topic = json.string("topic"),
            subject = json.stringOrNull("subject"),
            cards = json.getJSONArray("cards").mapObjects { card ->
                BackendFlashcard(
                    id = card.int("id"),
                    front = card.string("front"),
                    back = card.string("back"),
                    position = card.int("position"),
                )
            },
        )
    }

    suspend fun ask(question: String) = request(
        path = "/api/ask",
        method = "POST",
        body = JSONObject().put("question", question).put("subject", JSONObject.NULL),
    ) { json -> AskResponse(json.string("answer")) }

    suspend fun setTaskDone(id: Int, done: Boolean) = request(
        path = "/api/tasks/$id",
        method = "PATCH",
        body = JSONObject().put("done", done),
    ) { Unit }

    suspend fun objectRequest(
        path: String,
        method: String = "GET",
        body: JSONObject? = null,
    ): ApiResult<JSONObject> = request(path, method, body) { it }

    suspend fun arrayRequest(path: String): ApiResult<JSONArray> =
        requestArray(path) { it }

    suspend fun multipart(
        context: Context,
        path: String,
        field: String,
        uris: List<Uri>,
        fields: Map<String, String> = emptyMap(),
    ): ApiResult<JSONObject> = withContext(Dispatchers.IO) {
        val parts = uris.map { uri ->
            val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { cursor -> if (cursor.moveToFirst()) cursor.getString(0) else null }
                ?: "upload"
            UploadPart(field, name, context.contentResolver.getType(uri) ?: "application/octet-stream") {
                context.contentResolver.openInputStream(uri) ?: error("Cannot read $name")
            }
        }
        multipartRequest(path, parts, fields)
    }

    suspend fun multipartBytes(
        path: String,
        field: String,
        filename: String,
        mimeType: String,
        bytes: ByteArray,
        fields: Map<String, String> = emptyMap(),
    ): ApiResult<JSONObject> = withContext(Dispatchers.IO) {
        multipartRequest(path, listOf(UploadPart(field, filename, mimeType) { bytes.inputStream() }), fields)
    }

    suspend fun consumeEventStream(path: String): Unit = withContext(Dispatchers.IO) {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 180_000
            setRequestProperty("Accept", "text/event-stream")
        }
        try {
            if (connection.responseCode !in 200..299) throw ApiException(
                connection.responseCode,
                connection.getHeaderField("X-Request-ID"),
                connection.errorStream?.bufferedReader()?.use { it.readText() } ?: "OCR failed",
            )
            connection.inputStream.bufferedReader().useLines { lines -> lines.forEach { _ -> } }
        } finally {
            connection.disconnect()
        }
    }

    private fun multipartRequest(
        path: String,
        parts: List<UploadPart>,
        fields: Map<String, String>,
    ): ApiResult<JSONObject> {
        val boundary = "StudyBuddy-${UUID.randomUUID()}"
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 180_000
            doOutput = true
            setChunkedStreamingMode(256 * 1024)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("X-Request-ID", UUID.randomUUID().toString())
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        }
        try {
            DataOutputStream(connection.outputStream).use { output ->
                fun line(value: String = "") { output.write("$value\r\n".toByteArray()) }
                fields.forEach { (name, value) ->
                    line("--$boundary")
                    line("Content-Disposition: form-data; name=\"$name\"")
                    line()
                    line(value)
                }
                parts.forEach { part ->
                    line("--$boundary")
                    line("Content-Disposition: form-data; name=\"${part.field}\"; filename=\"${part.filename.replace("\"", "")}\"")
                    line("Content-Type: ${part.mimeType}")
                    line()
                    part.open().use { it.copyTo(output, 256 * 1024) }
                    line()
                }
                line("--$boundary--")
            }
            val status = connection.responseCode
            val requestId = connection.getHeaderField("X-Request-ID")
            val text = (if (status in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                throw ApiException(status, requestId, detail?.takeIf(String::isNotBlank) ?: "Upload failed")
            }
            return ApiResult(if (text.isBlank()) JSONObject() else JSONObject(text), requestId)
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun <T> get(path: String, decode: (JSONObject) -> T): ApiResult<T> =
        request(path, "GET", null, decode)

    private suspend fun <T> getArray(
        path: String,
        decode: (JSONObject) -> T,
    ): ApiResult<List<T>> = requestArray(path) { array ->
        array.mapObjects(decode)
    }

    private suspend fun <T> request(
        path: String,
        method: String,
        body: JSONObject?,
        decode: (JSONObject) -> T,
    ): ApiResult<T> = withContext(Dispatchers.IO) {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000
            readTimeout = 60_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("X-Request-ID", UUID.randomUUID().toString())
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
            }
        }
        try {
            val status = connection.responseCode
            val requestId = connection.getHeaderField("X-Request-ID")
            val text = (if (status in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                throw ApiException(status, requestId, detail?.takeIf(String::isNotBlank) ?: "Request failed")
            }
            val json = if (text.isBlank()) JSONObject() else JSONObject(text)
            ApiResult(decode(json), requestId)
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun <T> requestArray(
        path: String,
        decode: (JSONArray) -> T,
    ): ApiResult<T> = withContext(Dispatchers.IO) {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 60_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("X-Request-ID", UUID.randomUUID().toString())
        }
        try {
            val status = connection.responseCode
            val requestId = connection.getHeaderField("X-Request-ID")
            val text = (if (status in 200..299) connection.inputStream else connection.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                throw ApiException(status, requestId, detail?.takeIf(String::isNotBlank) ?: "Request failed")
            }
            ApiResult(decode(JSONArray(text)), requestId)
        } finally {
            connection.disconnect()
        }
    }
}

private data class UploadPart(
    val field: String,
    val filename: String,
    val mimeType: String,
    val open: () -> java.io.InputStream,
)

private fun JSONObject.int(name: String) = getInt(name)
private fun JSONObject.long(name: String) = getLong(name)
private fun JSONObject.double(name: String) = getDouble(name)
private fun JSONObject.string(name: String) = getString(name)
private fun JSONObject.stringOrNull(name: String): String? =
    if (isNull(name)) null else optString(name).takeIf { it.isNotBlank() }

private fun <T> JSONArray.mapObjects(transform: (JSONObject) -> T): List<T> =
    (0 until length()).map { transform(getJSONObject(it)) }
