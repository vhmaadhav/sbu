package com.example.mobile.ui.axiom

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import java.time.LocalTime
import java.time.format.DateTimeFormatter

val ScreenEasing = CubicBezierEasing(0.2f, 0.7f, 0.2f, 1f)

// Mono / Sans now live in AxiomType.kt — Sans is a composable getter so the
// dyslexia-friendly reading toggle can swap it everywhere at once.

@Composable
fun monoLabel(size: Int, color: Color, tracking: Float = 0.16f) = TextStyle(
    fontFamily = Mono,
    fontSize = size.sp,
    color = color,
    letterSpacing = tracking.em,
    fontWeight = FontWeight.Medium,
)

/** Click without ripple — the design language has no ripples, just color/scale motion. */
fun Modifier.axClick(onClick: () -> Unit): Modifier = this.then(
    Modifier.clickable(
        interactionSource = MutableInteractionSource(),
        indication = null,
        onClick = onClick,
    )
)

@Composable
fun AxiomApp() {
    val context = LocalContext.current
    val connectionPreferences = remember {
        context.getSharedPreferences("study_buddy_connection", android.content.Context.MODE_PRIVATE)
    }
    var apiBaseUrl by remember {
        mutableStateOf(connectionPreferences.getString("api_base_url", com.example.mobile.BuildConfig.API_BASE_URL)
            ?: com.example.mobile.BuildConfig.API_BASE_URL)
    }
    val viewModel: AxiomViewModel = viewModel()
    val backend by viewModel.data
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { viewModel.connect(apiBaseUrl) }
    val saveConnection: (String) -> Unit = { apiUrl ->
        val cleanApi = normalizeServerUrl(apiUrl)
        connectionPreferences.edit()
            .putString("api_base_url", cleanApi)
            .apply()
        apiBaseUrl = cleanApi
        viewModel.connect(cleanApi)
    }

    val appearancePreferences = remember {
        context.getSharedPreferences("study_buddy_appearance", android.content.Context.MODE_PRIVATE)
    }
    var dyslexic by remember {
        mutableStateOf(appearancePreferences.getBoolean("dyslexic_reading", false))
    }
    val setDyslexic: (Boolean) -> Unit = { on ->
        appearancePreferences.edit().putBoolean("dyslexic_reading", on).apply()
        dyslexic = on
    }

    var dark by remember { mutableStateOf(true) }
    val themeT by animateFloatAsState(
        targetValue = if (dark) 0f else 1f,
        animationSpec = tween(durationMillis = 420, easing = ScreenEasing),
        label = "theme",
    )
    val colors = lerp(AxiomDark, AxiomLight, themeT)

    var screen by remember { mutableStateOf(AxiomScreen.Home) }

    // Pomodoro timer
    var secs by remember { mutableIntStateOf(25 * 60) }
    var running by remember { mutableStateOf(false) }
    LaunchedEffect(running) {
        while (running && secs > 0) {
            delay(1000)
            secs -= 1
        }
        if (secs == 0) running = false
    }

    // AI assistant
    var query by remember { mutableStateOf("") }
    var aiOpen by remember { mutableStateOf(false) }
    var aiThinking by remember { mutableStateOf(false) }
    var aiAnswer by remember { mutableStateOf("") }
    val askAI = ask@{
        if (query.isBlank()) return@ask
        aiOpen = true
        aiThinking = true
        aiAnswer = ""
        val submitted = query
        scope.launch {
            viewModel.ask(submitted)
                .onSuccess { aiAnswer = it }
                .onFailure { aiAnswer = it.message ?: "The backend could not answer." }
            aiThinking = false
        }
    }

    // Resolved here rather than via the `Sans` getter: inside this argument
    // list LocalDyslexicReading still holds the *previous* value, since we are
    // in the middle of providing it.
    val bodyFont = if (dyslexic) OpenDyslexic else FontFamily.SansSerif

    CompositionLocalProvider(
        LocalAxiomColors provides colors,
        LocalDyslexicReading provides dyslexic,
        // Most Text calls pass only color/fontSize and inherit the rest, so the
        // ambient style is what carries the typeface swap across the app.
        LocalTextStyle provides LocalTextStyle.current.merge(TextStyle(fontFamily = bodyFont)),
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(colors.bg)
        ) {
            AmbientBackground(colors)

            Column(modifier = Modifier.fillMaxSize()) {
                Column(modifier = Modifier.statusBarsPadding()) {
                    StatusRow(colors, backend.stats != null)
                    TopBar(colors, dark) { dark = !dark }
                    AiBar(
                        colors = colors,
                        query = query,
                        onQueryChange = { query = it },
                        aiOpen = aiOpen,
                        aiThinking = aiThinking,
                        aiAnswer = aiAnswer,
                        onSubmit = askAI,
                        onClose = { aiOpen = false },
                    )
                }

                Box(modifier = Modifier.weight(1f)) {
                    AnimatedContent(
                        targetState = screen,
                        transitionSpec = {
                            (fadeIn(tween(380, easing = ScreenEasing)) +
                                slideInVertically(tween(380, easing = ScreenEasing)) { it / 24 })
                                .togetherWith(fadeOut(tween(120)))
                        },
                        label = "screen",
                    ) { current ->
                        when (current) {
                            AxiomScreen.Home -> HomeScreen(colors, backend, secs, running,
                                onToggleTimer = { running = !running },
                                onResetTimer = { running = false; secs = 25 * 60 },
                                onToggleTask = viewModel::toggleTask,
                                onRetry = viewModel::refresh)
                            AxiomScreen.Notes -> NotesScreen(colors, backend, apiBaseUrl, viewModel::refresh)
                            AxiomScreen.Cards -> CardsScreen(colors, backend, viewModel::selectDeck, viewModel::refresh)
                            AxiomScreen.Plan -> PlannerScreen(colors, backend, apiBaseUrl, viewModel::toggleTask, viewModel::refresh)
                            AxiomScreen.All -> NativeWorkspaceScreen(
                                colors = colors,
                                backend = backend,
                                apiBaseUrl = apiBaseUrl,
                                onSaveConnection = saveConnection,
                                onSetDyslexic = setDyslexic,
                                onRefreshCore = viewModel::refresh,
                            )
                        }
                    }
                }

                TabBar(colors, screen) { screen = it }
            }
        }
    }
}

private fun normalizeServerUrl(value: String): String {
    val trimmed = value.trim().trimEnd('/')
    if (trimmed.isBlank()) return trimmed
    return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed
    else "http://$trimmed"
}

/** Drifting glow blobs + faint blueprint grid behind everything. */
@Composable
private fun AmbientBackground(colors: AxiomColors) {
    val drift = rememberInfiniteTransition(label = "drift")
    val t1 by drift.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(16000, easing = LinearEasing), RepeatMode.Reverse),
        label = "blob1",
    )
    val t2 by drift.animateFloat(
        initialValue = 1f, targetValue = 0f,
        animationSpec = infiniteRepeatable(tween(20000, easing = LinearEasing), RepeatMode.Reverse),
        label = "blob2",
    )

    Box(
        modifier = Modifier
            .offset(x = (-40 + 30 * t1).dp, y = (-90 - 24 * t1).dp)
            .size(320.dp)
            .blur(26.dp)
            .background(
                Brush.radialGradient(
                    listOf(colors.accent.copy(alpha = 0.18f), Color.Transparent)
                )
            )
    )
    Box(modifier = Modifier.fillMaxSize()) {
        Box(
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .offset(x = (50 - 30 * t2).dp, y = (60 + 24 * t2).dp)
                .size(300.dp)
                .blur(26.dp)
                .background(Brush.radialGradient(listOf(colors.glow2, Color.Transparent)))
        )
    }
    Canvas(modifier = Modifier.fillMaxSize()) {
        val cell = 46.dp.toPx()
        val gridColor = colors.line.copy(alpha = colors.line.alpha * 0.28f)
        var x = 0f
        while (x < size.width) {
            drawLine(gridColor, Offset(x, 0f), Offset(x, size.height), strokeWidth = 1f)
            x += cell
        }
        var y = 0f
        while (y < size.height) {
            drawLine(gridColor, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
            y += cell
        }
    }
}

@Composable
private fun StatusRow(colors: AxiomColors, backendConnected: Boolean) {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val dotAlpha by pulse.animateFloat(
        initialValue = 1f, targetValue = 0.35f,
        animationSpec = infiniteRepeatable(tween(1200), RepeatMode.Reverse),
        label = "dot",
    )
    var time by remember { mutableStateOf(LocalTime.now().format(DateTimeFormatter.ofPattern("H:mm"))) }
    LaunchedEffect(Unit) {
        while (true) {
            time = LocalTime.now().format(DateTimeFormatter.ofPattern("H:mm"))
            delay(1_000)
        }
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 26.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(time, style = monoLabel(13, colors.text, tracking = 0.04f))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .graphicsLayer { alpha = dotAlpha }
                    .background(colors.accent, shape = androidx.compose.foundation.shape.CircleShape)
            )
            Text(
                if (backendConnected) "API LIVE" else "API OFFLINE",
                style = monoLabel(11, if (backendConnected) colors.dim else Color(0xFFF87171), tracking = 0.1f),
            )
        }
    }
}

@Composable
private fun TopBar(colors: AxiomColors, dark: Boolean, onToggleTheme: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 22.dp, end = 22.dp, top = 6.dp, bottom = 14.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(
                modifier = Modifier
                    .size(28.dp)
                    .border(1.dp, colors.accent)
                    .drawBehind {
                        drawRect(
                            Brush.radialGradient(
                                listOf(colors.accent.copy(alpha = 0.35f), Color.Transparent),
                                radius = size.width,
                            )
                        )
                    },
                contentAlignment = Alignment.Center,
            ) {
                Text("A", style = monoLabel(12, colors.accent, tracking = 0f))
            }
            Text(
                "AXIOM",
                style = TextStyle(
                    fontFamily = Sans,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = 0.16.em,
                    color = colors.text,
                ),
            )
        }

        // theme toggle
        val knob by animateFloatAsState(
            targetValue = if (dark) 0f else 1f,
            animationSpec = tween(250, easing = ScreenEasing),
            label = "knob",
        )
        Box(
            modifier = Modifier
                .size(width = 38.dp, height = 20.dp)
                .border(1.dp, colors.line2, androidx.compose.foundation.shape.RoundedCornerShape(20.dp))
                .axClick(onToggleTheme)
        ) {
            Box(
                modifier = Modifier
                    .offset(x = (2 + 18 * knob).dp, y = 2.dp)
                    .size(14.dp)
                    .background(colors.accent, androidx.compose.foundation.shape.CircleShape)
                    .drawBehind {
                        drawCircle(colors.accent.copy(alpha = 0.4f), radius = size.width * 0.9f)
                    }
            )
        }
    }
}

@Composable
private fun AiBar(
    colors: AxiomColors,
    query: String,
    onQueryChange: (String) -> Unit,
    aiOpen: Boolean,
    aiThinking: Boolean,
    aiAnswer: String,
    onSubmit: () -> Unit,
    onClose: () -> Unit,
) {
    val borderColor = if (aiOpen) colors.accent else colors.line
    Column(modifier = Modifier.padding(start = 20.dp, end = 20.dp, bottom = 12.dp)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .border(1.dp, borderColor)
                .background(colors.panel2)
                .padding(horizontal = 13.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Text("›", style = monoLabel(13, colors.accent, tracking = 0f))
            Box(modifier = Modifier.weight(1f)) {
                if (query.isEmpty()) {
                    Text(
                        "Ask Axiom anything…",
                        style = TextStyle(fontFamily = Sans, fontSize = 13.sp, color = colors.dim),
                    )
                }
                BasicTextField(
                    value = query,
                    onValueChange = onQueryChange,
                    singleLine = true,
                    textStyle = TextStyle(fontFamily = Sans, fontSize = 13.sp, color = colors.text),
                    cursorBrush = SolidColor(colors.accent),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { onSubmit() }),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Box(
                modifier = Modifier
                    .border(1.dp, if (aiOpen) colors.accent else colors.line2)
                    .axClick(onSubmit)
                    .padding(horizontal = 7.dp, vertical = 3.dp)
            ) {
                Text("AI", style = monoLabel(9, if (aiOpen) colors.accent else colors.faint, tracking = 0.14f))
            }
        }

        AnimatedVisibility(
            visible = aiOpen,
            enter = fadeIn(tween(280, easing = ScreenEasing)) + expandVertically(tween(280, easing = ScreenEasing)),
            exit = fadeOut(tween(160)) + shrinkVertically(tween(200, easing = ScreenEasing)),
        ) {
            Column(
                modifier = Modifier
                    .padding(top = 8.dp)
                    .fillMaxWidth()
                    .border(1.dp, colors.accent)
                    .background(colors.panel)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("AXIOM AI", style = monoLabel(9, colors.accent, tracking = 0.18f))
                    Text("✕", style = monoLabel(11, colors.dim, tracking = 0f), modifier = Modifier.axClick(onClose))
                }
                HairlineDivider(colors.line)
                Box(modifier = Modifier.padding(14.dp)) {
                    if (aiThinking) {
                        val pulse = rememberInfiniteTransition(label = "thinking")
                        val a by pulse.animateFloat(
                            initialValue = 1f, targetValue = 0.35f,
                            animationSpec = infiniteRepeatable(tween(500), RepeatMode.Reverse),
                            label = "dots",
                        )
                        Row {
                            Text("ANALYZING", style = monoLabel(11, colors.dim, tracking = 0.16f))
                            Text("…", style = monoLabel(11, colors.dim, tracking = 0f), modifier = Modifier.graphicsLayer { alpha = a })
                        }
                    } else if (aiAnswer.isNotEmpty()) {
                        MarkdownText(aiAnswer, colors, fontSize = 13.sp, lineHeight = 21.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun HairlineDivider(color: Color) {
    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(color))
}

@Composable
private fun TabBar(colors: AxiomColors, current: AxiomScreen, onSelect: (AxiomScreen) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.panel)
    ) {
        HairlineDivider(colors.line)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(top = 10.dp, bottom = 10.dp, start = 18.dp, end = 18.dp),
            horizontalArrangement = Arrangement.SpaceAround,
        ) {
            AxiomScreen.entries.forEach { tab ->
                TabItem(colors, tab, selected = tab == current) { onSelect(tab) }
            }
        }
    }
}

@Composable
private fun TabItem(colors: AxiomColors, tab: AxiomScreen, selected: Boolean, onClick: () -> Unit) {
    // iconPop: overshoot up to -6dp / 1.28x then settle at -3dp / 1.14x
    val lift by animateFloatAsState(
        targetValue = if (selected) 1f else 0f,
        animationSpec = if (selected) {
            androidx.compose.animation.core.keyframes {
                durationMillis = 420
                0f at 0
                2f at 230 using ScreenEasing
                1f at 420 using ScreenEasing
            }
        } else tween(250, easing = ScreenEasing),
        label = "tabLift",
    )
    val color = lerp(colors.dim, colors.accent, lift.coerceIn(0f, 1f))
    val icon = when (tab) {
        AxiomScreen.Home -> IconHome
        AxiomScreen.Notes -> IconNotes
        AxiomScreen.Cards -> IconCards
        AxiomScreen.Plan -> IconPlan
        AxiomScreen.All -> IconAll
    }
    Column(
        modifier = Modifier
            .axClick(onClick)
            .padding(horizontal = 14.dp, vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(contentAlignment = Alignment.Center) {
            // glow behind selected icon
            Box(
                modifier = Modifier
                    .size(30.dp)
                    .graphicsLayer { alpha = lift.coerceIn(0f, 1f) * 0.55f }
                    .background(
                        Brush.radialGradient(listOf(colors.accent.copy(alpha = 0.6f), Color.Transparent))
                    )
            )
            Icon(
                imageVector = icon,
                contentDescription = tab.label,
                tint = color,
                modifier = Modifier
                    .size(23.dp)
                    .graphicsLayer {
                        translationY = -3.dp.toPx() * lift
                        val s = 1f + 0.14f * lift
                        scaleX = s
                        scaleY = s
                    },
            )
        }
        Text(tab.label, style = monoLabel(8, color, tracking = 0.14f))
    }
}

private fun lerp(a: Color, b: Color, t: Float): Color = androidx.compose.ui.graphics.lerp(a, b, t)
