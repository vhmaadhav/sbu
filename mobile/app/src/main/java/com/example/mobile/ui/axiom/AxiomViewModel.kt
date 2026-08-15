package com.example.mobile.ui.axiom

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.mobile.network.ApiException
import com.example.mobile.network.StudyBuddyApi
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch

class AxiomViewModel(private var api: StudyBuddyApi = StudyBuddyApi()) : ViewModel() {
    var data = androidx.compose.runtime.mutableStateOf(MobileData())
        private set

    fun refresh() {
        viewModelScope.launch {
            data.value = data.value.copy(loading = true, error = null)
            try {
                // coroutineScope contains async failures: a failed fetch rethrows
                // here (caught below) instead of killing the whole process.
                coroutineScope {
                    val stats = async { api.stats() }
                    val notes = async { api.notes() }
                    val tasks = async { api.tasks() }
                    val decks = async { api.decks() }
                    val statResult = stats.await()
                    val noteResult = notes.await()
                    val taskResult = tasks.await()
                    val deckResult = decks.await()
                    val firstDeck = deckResult.value.firstOrNull()?.let { api.deck(it.id) }
                    data.value = MobileData(
                        stats = statResult.value,
                        notes = noteResult.value,
                        tasks = taskResult.value,
                        decks = deckResult.value,
                        selectedDeck = firstDeck?.value,
                        loading = false,
                        lastRequestId = firstDeck?.requestId ?: deckResult.requestId,
                    )
                }
            } catch (error: Exception) {
                fail(error)
            }
        }
    }

    fun connect(apiBaseUrl: String) {
        api = StudyBuddyApi(apiBaseUrl)
        refresh()
    }

    fun selectDeck(id: Int) {
        viewModelScope.launch {
            try {
                val result = api.deck(id)
                data.value = data.value.copy(selectedDeck = result.value, lastRequestId = result.requestId)
            } catch (error: Exception) {
                fail(error)
            }
        }
    }

    fun toggleTask(task: BackendTask) {
        viewModelScope.launch {
            try {
                val result = api.setTaskDone(task.id, !task.done)
                data.value = data.value.copy(
                    tasks = data.value.tasks.map {
                        if (it.id == task.id) it.copy(done = !task.done) else it
                    },
                    lastRequestId = result.requestId,
                )
            } catch (error: Exception) {
                fail(error)
            }
        }
    }

    suspend fun ask(question: String): Result<String> = runCatching {
        val result = api.ask(question)
        data.value = data.value.copy(lastRequestId = result.requestId, error = null)
        result.value.answer
    }

    private fun fail(error: Throwable) {
        val apiError = error as? ApiException
        data.value = data.value.copy(
            loading = false,
            error = buildString {
                append(error.message ?: "Could not reach the Study Buddy backend")
                apiError?.requestId?.let { append(" · request $it") }
            },
            lastRequestId = apiError?.requestId ?: data.value.lastRequestId,
        )
    }
}
