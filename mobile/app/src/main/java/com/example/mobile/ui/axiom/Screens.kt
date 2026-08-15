package com.example.mobile.ui.axiom

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.example.mobile.network.StudyBuddyApi
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.WeekFields
import java.util.Locale

private val ScreenPadding = Modifier.padding(horizontal = 20.dp)
private typealias ColumnScopeAlias = androidx.compose.foundation.layout.ColumnScope

@Composable
private fun ScreenColumn(gap: Int, content: @Composable ColumnScopeAlias.() -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .then(ScreenPadding)
            .padding(top = 4.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(gap.dp),
        content = content,
    )
}

@Composable
private fun BackendState(data: MobileData, colors: AxiomColors, onRetry: () -> Unit) {
    when {
        data.loading -> Text("SYNCING WITH BACKEND…", style = monoLabel(10, colors.dim, 0.12f))
        data.error != null -> Column(
            modifier = Modifier.fillMaxWidth().border(1.dp, Color(0xFFF87171)).padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(data.error, style = TextStyle(fontFamily = Sans, fontSize = 12.sp, color = Color(0xFFF87171)))
            Text("RETRY", style = monoLabel(10, colors.accent, 0.16f), modifier = Modifier.axClick(onRetry))
        }
    }
}

@Composable
fun HomeScreen(
    colors: AxiomColors,
    data: MobileData,
    secs: Int,
    running: Boolean,
    onToggleTimer: () -> Unit,
    onResetTimer: () -> Unit,
    onToggleTask: (BackendTask) -> Unit,
    onRetry: () -> Unit,
) {
    val today = LocalDate.now()
    val openTasks = data.tasks.filterNot { it.done }
    ScreenColumn(gap = 18) {
        Column {
            Text(
                today.format(DateTimeFormatter.ofPattern("EEE · MMM d", Locale.getDefault())).uppercase(),
                style = monoLabel(10, colors.accent, tracking = 0.22f),
            )
            Spacer(Modifier.height(6.dp))
            Text(
                "Study Buddy",
                style = TextStyle(fontFamily = Sans, fontSize = 24.sp, fontWeight = FontWeight.Medium, color = colors.text),
            )
            Spacer(Modifier.height(6.dp))
            Text(
                if (data.loading) "Loading your workspace…"
                else data.stats?.let { "${openTasks.size} open tasks · ${it.flashcards} flashcards." }
                    ?: "Backend data unavailable.",
                style = TextStyle(fontFamily = Sans, fontSize = 13.sp, color = colors.dim),
            )
        }
        BackendState(data, colors, onRetry)
        data.stats?.let { StatsGrid(colors, it) }
        TimerCard(colors, secs, running, onToggleTimer, onResetTimer)
        TodaysPlan(colors, data.tasks, onToggleTask)
    }
}

@Composable
private fun StatsGrid(colors: AxiomColors, stats: BackendStats) {
    val values = listOf(
        Triple("NOTES", stats.notes.toString(), false),
        Triple("MATERIALS", stats.files.toString(), true),
        Triple("FLASHCARDS", stats.flashcards.toString(), false),
        Triple("AUDIOBOOKS", stats.audiobooks.toString(), false),
    )
    Column(
        modifier = Modifier.fillMaxWidth().border(1.dp, colors.line).background(colors.line),
        verticalArrangement = Arrangement.spacedBy(1.dp),
    ) {
        values.chunked(2).forEach { rowStats ->
            Row(
                modifier = Modifier.fillMaxWidth().height(IntrinsicSize.Min),
                horizontalArrangement = Arrangement.spacedBy(1.dp),
            ) {
                rowStats.forEach { stat ->
                    Column(
                        modifier = Modifier.weight(1f).fillMaxHeight().background(colors.panel).padding(16.dp)
                    ) {
                        Text(stat.first, style = monoLabel(9, colors.dim, tracking = 0.16f))
                        Spacer(Modifier.height(8.dp))
                        Text(
                            stat.second,
                            style = TextStyle(
                                fontFamily = Mono,
                                fontSize = 24.sp,
                                fontWeight = FontWeight.Medium,
                                color = if (stat.third) colors.accent else colors.text,
                            ),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TimerCard(
    colors: AxiomColors,
    secs: Int,
    running: Boolean,
    onToggle: () -> Unit,
    onReset: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth().border(1.dp, colors.accent).background(colors.panel).padding(20.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("FOCUS TIMER", style = monoLabel(10, colors.dim, tracking = 0.2f))
            Text("ON DEVICE", style = monoLabel(10, colors.faint, tracking = 0.16f))
        }
        Spacer(Modifier.height(14.dp))
        Text(
            "${(secs / 60).toString().padStart(2, '0')}:${(secs % 60).toString().padStart(2, '0')}",
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            style = TextStyle(
                fontFamily = Mono, fontSize = 42.sp, fontWeight = FontWeight.Light,
                letterSpacing = 0.04.em, color = colors.text,
            ),
        )
        Spacer(Modifier.height(16.dp))
        val progress by animateFloatAsState(1f - secs / 1500f, tween(1000), label = "timerProgress")
        ProgressLine(colors, progress)
        Spacer(Modifier.height(16.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ActionButton(colors, if (running) "PAUSE" else "START", Modifier.weight(1f), onToggle)
            ActionButton(colors, "RESET", Modifier, onReset)
        }
    }
}

@Composable
private fun ActionButton(
    colors: AxiomColors,
    label: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Box(
        modifier = modifier.border(1.dp, colors.accent).axClick(onClick).padding(vertical = 11.dp, horizontal = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, style = monoLabel(11, colors.accent, tracking = 0.2f))
    }
}

@Composable
fun ProgressLine(colors: AxiomColors, fraction: Float) {
    Box(modifier = Modifier.fillMaxWidth().height(2.dp).background(colors.line)) {
        Box(Modifier.fillMaxWidth(fraction.coerceIn(0f, 1f)).height(2.dp).background(colors.accent))
    }
}

@Composable
private fun TodaysPlan(colors: AxiomColors, tasks: List<BackendTask>, onToggle: (BackendTask) -> Unit) {
    Column(modifier = Modifier.fillMaxWidth().border(1.dp, colors.line).background(colors.panel)) {
        Text(
            "TASKS",
            style = monoLabel(10, colors.dim, tracking = 0.2f),
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp),
        )
        if (tasks.isEmpty()) {
            HairlineDivider(colors.line)
            Text("No tasks from the backend.", Modifier.padding(18.dp), color = colors.dim, fontSize = 13.sp)
        }
        tasks.take(6).forEach { task ->
            HairlineDivider(colors.line)
            Row(
                modifier = Modifier.fillMaxWidth().axClick { onToggle(task) }.padding(horizontal = 18.dp, vertical = 13.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Box(
                    Modifier.size(9.dp).border(1.dp, colors.accent)
                        .background(if (task.done) colors.accent else Color.Transparent)
                )
                Column(Modifier.weight(1f)) {
                    Text(
                        task.label,
                        style = TextStyle(
                            fontFamily = Sans, fontSize = 13.sp,
                            color = if (task.done) colors.faint else colors.text,
                            textDecoration = if (task.done) TextDecoration.LineThrough else null,
                        ),
                    )
                    task.due?.let { Text(it, style = monoLabel(9, colors.dim, 0.04f)) }
                }
            }
        }
    }
}

@Composable
fun NotesScreen(colors: AxiomColors, data: MobileData, apiBaseUrl: String, onRetry: () -> Unit) {
    var search by remember { mutableStateOf("") }
    var selectedNoteId by remember { mutableStateOf<Int?>(null) }
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var detailError by remember { mutableStateOf("") }
    var detailReload by remember { mutableIntStateOf(0) }
    val api = remember(apiBaseUrl) { StudyBuddyApi(apiBaseUrl) }
    LaunchedEffect(selectedNoteId, api, detailReload) {
        detail = null
        detailError = ""
        selectedNoteId?.let { id ->
            runCatching { api.objectRequest("/api/notes/$id").value }
                .onSuccess { detail = it }
                .onFailure { detailError = it.message ?: "Could not load this note." }
        }
    }
    val filtered = data.notes.filter {
        search.isBlank() ||
            it.title.orEmpty().contains(search, ignoreCase = true) ||
            it.preview.contains(search, ignoreCase = true) ||
            it.subject.orEmpty().contains(search, ignoreCase = true)
    }
    ScreenColumn(gap = 14) {
        if (selectedNoteId != null) {
            Text("‹ NOTES", style = monoLabel(10, colors.accent, 0.14f), modifier = Modifier.axClick { selectedNoteId = null })
            when {
                detailError.isNotBlank() -> {
                    Text(detailError, color = Color(0xFFF87171), fontSize = 12.sp)
                    Text("RETRY", style = monoLabel(10, colors.accent, 0.14f), modifier = Modifier.axClick {
                        detailReload++
                    })
                }
                detail == null -> Text("LOADING FULL NOTE…", style = monoLabel(10, colors.dim, 0.12f))
                else -> {
                    val note = detail ?: return@ScreenColumn
                    Text(
                        note.optString("title").ifBlank { "Untitled" },
                        style = TextStyle(fontFamily = Sans, fontSize = 22.sp, fontWeight = FontWeight.Medium, color = colors.text),
                    )
                    Text(
                        listOf(note.optString("subject").ifBlank { "Unfiled" }, timeAgo(note.optLong("created_at")))
                            .joinToString(" · ").uppercase(),
                        style = monoLabel(9, colors.faint, 0.1f),
                    )
                    note.optJSONArray("images")?.let { images ->
                        for (index in 0 until images.length()) {
                            val image = images.getJSONObject(index)
                            RemoteImage("$apiBaseUrl${image.optString("url")}", 240)
                            image.optString("caption").takeIf { it.isNotBlank() }?.let {
                                Text(it, color = colors.dim, fontSize = 10.sp)
                            }
                        }
                    }
                    MarkdownText(note.optString("markdown"), colors)
                }
            }
            return@ScreenColumn
        }
        Text("Notes", style = TextStyle(fontFamily = Sans, fontSize = 22.sp, fontWeight = FontWeight.Medium, color = colors.text))
        BackendState(data, colors, onRetry)
        Box(
            Modifier.fillMaxWidth().background(colors.panel2).border(1.dp, colors.line)
                .padding(horizontal = 14.dp, vertical = 10.dp)
        ) {
            if (search.isEmpty()) Text("Search live notes…", style = monoLabel(11, colors.dim, tracking = 0f))
            BasicTextField(
                value = search,
                onValueChange = { search = it },
                singleLine = true,
                textStyle = TextStyle(fontFamily = Mono, fontSize = 11.sp, color = colors.text),
                cursorBrush = SolidColor(colors.accent),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (!data.loading && filtered.isEmpty()) {
            Text("No matching notes in the backend.", color = colors.dim, fontSize = 13.sp)
        }
        filtered.forEach { note ->
            Column(
                Modifier.fillMaxWidth().border(1.dp, colors.line).background(colors.panel)
                    .drawAccentEdge(colors.accent).axClick { selectedNoteId = note.id }
                    .padding(start = 16.dp, end = 16.dp, top = 15.dp, bottom = 15.dp)
            ) {
                Text(
                    note.title ?: "Untitled",
                    style = TextStyle(fontFamily = Sans, fontSize = 14.sp, fontWeight = FontWeight.Medium, color = colors.text),
                )
                Spacer(Modifier.height(5.dp))
                Text(
                    note.preview, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    style = TextStyle(fontFamily = Sans, fontSize = 12.sp, color = colors.dim),
                )
                Spacer(Modifier.height(9.dp))
                Text(
                    listOfNotNull(note.subject, timeAgo(note.createdAt)).joinToString(" · ").uppercase(),
                    style = monoLabel(9, colors.faint, tracking = 0.12f),
                )
            }
        }
    }
}

private fun Modifier.drawAccentEdge(accent: Color): Modifier =
    drawBehind { drawRect(accent, size = Size(2.dp.toPx(), size.height)) }

@Composable
fun CardsScreen(
    colors: AxiomColors,
    data: MobileData,
    onSelectDeck: (Int) -> Unit,
    onRetry: () -> Unit,
) {
    var idx by remember(data.selectedDeck?.id) { mutableIntStateOf(0) }
    var flipped by remember(data.selectedDeck?.id) { mutableStateOf(false) }
    val deck = data.selectedDeck
    val card = deck?.cards?.getOrNull(idx)

    ScreenColumn(gap = 16) {
        Text("Flashcards", style = TextStyle(fontFamily = Sans, fontSize = 22.sp, fontWeight = FontWeight.Medium, color = colors.text))
        BackendState(data, colors, onRetry)
        if (data.decks.isEmpty() && !data.loading) {
            Text("No flashcard decks exist in the backend. Create one by asking Axiom AI.", color = colors.dim, fontSize = 13.sp)
        }
        data.decks.forEach { summary ->
            Row(
                Modifier.fillMaxWidth()
                    .border(1.dp, if (summary.id == deck?.id) colors.accent else colors.line)
                    .axClick { onSelectDeck(summary.id) }.padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(summary.title, color = colors.text, fontSize = 13.sp, modifier = Modifier.weight(1f))
                Text("${summary.cardCount} CARDS", style = monoLabel(9, colors.dim, 0.08f))
            }
        }
        if (deck != null && card != null) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text((deck.subject ?: deck.topic).uppercase(), style = monoLabel(10, colors.dim, 0.12f))
                Text("${idx + 1} / ${deck.cards.size}", style = monoLabel(10, colors.dim, 0.12f))
            }
            ProgressLine(colors, (idx + 1) / deck.cards.size.toFloat())
            val rotation by animateFloatAsState(if (flipped) 180f else 0f, tween(500, easing = ScreenEasing), label = "flip")
            val showingBack = rotation > 90f
            AnimatedContent(
                targetState = idx,
                transitionSpec = {
                    (fadeIn(tween(300)) + slideInHorizontally { it / 8 })
                        .togetherWith(fadeOut(tween(120)) + slideOutHorizontally { -it / 12 })
                },
                label = "cardSwap",
            ) {
                Box(
                    Modifier.fillMaxWidth().heightIn(min = 320.dp)
                        .graphicsLayer { rotationY = rotation; cameraDistance = 12f * density }
                        .border(1.dp, if (showingBack) colors.accent else colors.line2)
                        .background(colors.panel).axClick { flipped = !flipped }.padding(28.dp)
                ) {
                    Box(Modifier.fillMaxSize().graphicsLayer { if (showingBack) rotationY = 180f }) {
                        Text(if (showingBack) "ANSWER" else "QUESTION", style = monoLabel(9, colors.faint, 0.2f))
                        Text(
                            markdownAnnotated(if (showingBack) card.back else card.front, colors),
                            modifier = Modifier.align(Alignment.Center),
                            textAlign = TextAlign.Center,
                            style = TextStyle(
                                fontFamily = Sans, fontSize = 18.sp, fontWeight = FontWeight.Medium,
                                lineHeight = 27.sp, color = colors.text,
                            ),
                        )
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ActionButton(colors, "PREVIOUS", Modifier.weight(1f)) {
                    idx = (idx - 1 + deck.cards.size) % deck.cards.size
                    flipped = false
                }
                ActionButton(colors, "NEXT", Modifier.weight(1f)) {
                    idx = (idx + 1) % deck.cards.size
                    flipped = false
                }
            }
        }
    }
}

@Composable
fun PlannerScreen(
    colors: AxiomColors,
    data: MobileData,
    apiBaseUrl: String,
    onToggleTask: (BackendTask) -> Unit,
    onRetry: () -> Unit,
) {
    val context = LocalContext.current
    val today = LocalDate.now()
    val week = today.get(WeekFields.of(Locale.getDefault()).weekOfWeekBasedYear())
    val api = remember(apiBaseUrl) { StudyBuddyApi(apiBaseUrl) }

    var visibleMonth by remember { mutableStateOf(today.withDayOfMonth(1)) }
    var selectedDate by remember { mutableStateOf(today) }
    var events by remember { mutableStateOf<List<JSONObject>>(emptyList()) }

    // Google events are a bonus here: the planner still works from tasks alone when
    // the backend is unreachable or the calendar was never connected.
    LaunchedEffect(visibleMonth, apiBaseUrl) {
        events = runCatching {
            val zone = ZoneId.systemDefault()
            val start = visibleMonth.atStartOfDay(zone).toInstant().toString()
            val end = visibleMonth.plusMonths(1).atStartOfDay(zone).toInstant().toString()
            api.arrayRequest(
                "/api/calendar/google/events?time_min=${enc(start)}&time_max=${enc(end)}"
            ).value.objects()
        }.getOrDefault(emptyList())
    }

    val markers = dayMarkers(
        taskDues = data.tasks.map { it.due },
        eventStarts = events.map { it.optString("start") },
    )
    val tasksForDay = data.tasks.filter { taskDueDate(it.due) == selectedDate }
    val eventsForDay = events.filter { eventLocalDate(it.optString("start")) == selectedDate }
    val undated = data.tasks.filter { taskDueDate(it.due) == null }

    ScreenColumn(gap = 14) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
            Text("Week $week", style = TextStyle(fontFamily = Sans, fontSize = 22.sp, fontWeight = FontWeight.Medium, color = colors.text))
            Text(today.format(DateTimeFormatter.ofPattern("MMM yyyy")).uppercase(), style = monoLabel(10, colors.dim, 0.14f))
        }
        BackendState(data, colors, onRetry)

        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("‹", style = monoLabel(18, colors.accent, 0f), modifier = Modifier.axClick {
                visibleMonth = visibleMonth.minusMonths(1)
            })
            Text(
                visibleMonth.format(DateTimeFormatter.ofPattern("MMMM yyyy", Locale.getDefault())),
                style = TextStyle(fontFamily = Sans, fontSize = 16.sp, fontWeight = FontWeight.Medium, color = colors.text),
            )
            Text("›", style = monoLabel(18, colors.accent, 0f), modifier = Modifier.axClick {
                visibleMonth = visibleMonth.plusMonths(1)
            })
        }
        MonthGrid(
            colors = colors,
            month = visibleMonth,
            selectedDate = selectedDate,
            eventCounts = markers,
            onSelect = { date ->
                selectedDate = date
                if (date.month != visibleMonth.month || date.year != visibleMonth.year) {
                    visibleMonth = date.withDayOfMonth(1)
                }
            },
        )

        Text(
            selectedDate.format(DateTimeFormatter.ofPattern("EEEE, d MMMM", Locale.getDefault())),
            style = TextStyle(fontFamily = Sans, fontSize = 15.sp, fontWeight = FontWeight.Medium, color = colors.text),
        )
        if (tasksForDay.isEmpty() && eventsForDay.isEmpty()) {
            Text("Nothing scheduled on this day.", color = colors.dim, fontSize = 12.sp)
        }
        eventsForDay.forEach { event ->
            CalendarEventCard(colors, context, event)
        }
        tasksForDay.forEach { task ->
            PlannerTaskRow(colors, task, onToggleTask)
        }

        if (undated.isNotEmpty()) {
            Text("No due date", style = monoLabel(10, colors.dim, 0.12f))
        }
        undated.forEach { task ->
            PlannerTaskRow(colors, task, onToggleTask)
        }
    }
}

@Composable
private fun PlannerTaskRow(
    colors: AxiomColors,
    task: BackendTask,
    onToggleTask: (BackendTask) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().border(1.dp, colors.line).background(colors.panel)
            .axClick { onToggleTask(task) }.padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier.size(10.dp).border(1.dp, colors.accent)
                .background(if (task.done) colors.accent else Color.Transparent)
        )
        Column(Modifier.weight(1f)) {
            Text(
                task.label,
                style = TextStyle(
                    fontFamily = Sans, fontSize = 13.sp, color = if (task.done) colors.faint else colors.text,
                    textDecoration = if (task.done) TextDecoration.LineThrough else null,
                ),
            )
            Text(task.due ?: "No due date", style = monoLabel(9, colors.dim, 0.04f))
        }
    }
}

private fun timeAgo(timestampSeconds: Long): String {
    val seconds = (Instant.now().epochSecond - timestampSeconds).coerceAtLeast(0)
    return when {
        seconds < 60 -> "just now"
        seconds < 3600 -> "${seconds / 60}m ago"
        seconds < 86_400 -> "${seconds / 3600}h ago"
        else -> "${seconds / 86_400}d ago"
    }
}
