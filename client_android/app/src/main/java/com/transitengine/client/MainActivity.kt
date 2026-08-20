package com.transitengine.client

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    RouteScreen()
                }
            }
        }
    }
}

// ── Utility ────────────────────────────────────────────────────
private fun formatSeconds(seconds: Int): String {
    val h = seconds / 3600
    val m = (seconds % 3600) / 60
    return "%02d:%02d".format(h, m)
}

// ── Main Screen ────────────────────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RouteScreen(viewModel: RouteViewModel = viewModel()) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Transit Route Finder") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                )
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // ── Source stop autocomplete ────────────────────────
            StopAutocomplete(
                query = viewModel.sourceQuery,
                onQueryChange = viewModel::onSourceQueryChanged,
                stops = viewModel.stops,
                onSelected = viewModel::onSourceSelected,
                label = "Source Stop"
            )

            // ── Target stop autocomplete ───────────────────────
            StopAutocomplete(
                query = viewModel.targetQuery,
                onQueryChange = viewModel::onTargetQueryChanged,
                stops = viewModel.stops,
                onSelected = viewModel::onTargetSelected,
                label = "Target Stop"
            )

            // ── Departure time picker ──────────────────────────
            DepartureTimePicker(
                displayText = viewModel.formatDepartureTime(),
                onTimeSelected = viewModel::onDepartureTimeSelected
            )

            // ── Find Route button ──────────────────────────────
            Button(
                onClick = viewModel::findRoute,
                enabled = !viewModel.isLoading
                        && viewModel.selectedSource != null
                        && viewModel.selectedTarget != null
                        && viewModel.departureSeconds >= 0,
                modifier = Modifier.fillMaxWidth()
            ) {
                if (viewModel.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                }
                Text("Find Route")
            }

            // ── Error message ──────────────────────────────────
            if (viewModel.errorMessage.isNotEmpty()) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = viewModel.errorMessage,
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }

            // ── Itinerary cards ────────────────────────────────
            if (viewModel.legs.isNotEmpty()) {
                Text(
                    text = "Itinerary",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(top = 4.dp)
                )

                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    itemsIndexed(viewModel.legs) { index, leg ->
                        LegCard(
                            index = index + 1,
                            leg = leg,
                            stopName = viewModel::stopName
                        )
                    }
                }
            }
        }
    }
}

// ── Stop Autocomplete ──────────────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StopAutocomplete(
    query: String,
    onQueryChange: (String) -> Unit,
    stops: List<Stop>,
    onSelected: (Stop) -> Unit,
    label: String
) {
    var expanded by remember { mutableStateOf(false) }

    val filtered = remember(query, stops) {
        if (query.isBlank()) {
            stops.take(50)
        } else {
            stops.filter {
                it.name.contains(query, ignoreCase = true)
            }.take(50)
        }
    }

    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = it }
    ) {
        OutlinedTextField(
            value = query,
            onValueChange = {
                onQueryChange(it)
                expanded = true
            },
            label = { Text(label) },
            singleLine = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            colors = ExposedDropdownMenuDefaults.outlinedTextFieldColors(),
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(MenuAnchorType.PrimaryEditable)
        )

        ExposedDropdownMenu(
            expanded = expanded && filtered.isNotEmpty(),
            onDismissRequest = { expanded = false }
        ) {
            filtered.forEach { stop ->
                DropdownMenuItem(
                    text = { Text(stop.name) },
                    onClick = {
                        onSelected(stop)
                        expanded = false
                    },
                    contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding
                )
            }
        }
    }
}

// ── Departure Time Picker ──────────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DepartureTimePicker(
    displayText: String,
    onTimeSelected: (hour: Int, minute: Int) -> Unit
) {
    var showDialog by remember { mutableStateOf(false) }
    val timePickerState = rememberTimePickerState()

    OutlinedTextField(
        value = if (displayText.isNotEmpty()) displayText else "Select departure time",
        onValueChange = {},
        label = { Text("Departure Time") },
        readOnly = true,
        singleLine = true,
        trailingIcon = {
            IconButton(onClick = { showDialog = true }) {
                Icon(Icons.Outlined.AccessTime, contentDescription = "Pick time")
            }
        },
        modifier = Modifier.fillMaxWidth()
    )

    if (showDialog) {
        AlertDialog(
            onDismissRequest = { showDialog = false },
            confirmButton = {
                TextButton(onClick = {
                    onTimeSelected(timePickerState.hour, timePickerState.minute)
                    showDialog = false
                }) {
                    Text("Confirm")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDialog = false }) {
                    Text("Cancel")
                }
            },
            title = { Text("Select Departure Time") },
            text = {
                Box(
                    modifier = Modifier.fillMaxWidth(),
                    contentAlignment = Alignment.Center
                ) {
                    TimePicker(state = timePickerState)
                }
            }
        )
    }
}

// ── Itinerary Leg Card ─────────────────────────────────────────
@Composable
fun LegCard(
    index: Int,
    leg: Leg,
    stopName: (Int) -> String
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header row: leg number + route badge
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "Leg $index",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSecondaryContainer
                )
                AssistChip(
                    onClick = {},
                    label = {
                        Text(
                            "Route ${leg.routeId}",
                            style = MaterialTheme.typography.labelMedium
                        )
                    }
                )
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Board → Alight row
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth()
            ) {
                // Board info
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Board",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                    )
                    Text(
                        text = stopName(leg.boardStop.toInt()),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSecondaryContainer
                    )
                    Text(
                        text = formatSeconds(leg.boardTime.toInt()),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                    )
                }

                Icon(
                    imageVector = Icons.AutoMirrored.Outlined.ArrowForward,
                    contentDescription = "to",
                    tint = MaterialTheme.colorScheme.onSecondaryContainer,
                    modifier = Modifier.padding(horizontal = 8.dp)
                )

                // Alight info
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Alight",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                    )
                    Text(
                        text = stopName(leg.alightStop.toInt()),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSecondaryContainer
                    )
                    Text(
                        text = formatSeconds(leg.alightTime.toInt()),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                    )
                }
            }
        }
    }
}
