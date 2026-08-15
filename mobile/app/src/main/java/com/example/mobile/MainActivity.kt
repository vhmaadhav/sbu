package com.example.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.runtime.Composable
import com.example.mobile.ui.axiom.AxiomApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AxiomApp()
        }
    }
}

@Preview(showBackground = true, showSystemUi = true)
@Composable
fun AxiomPreview() {
    AxiomApp()
}
