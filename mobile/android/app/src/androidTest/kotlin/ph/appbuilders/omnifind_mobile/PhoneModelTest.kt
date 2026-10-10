package ph.appbuilders.omnifind_mobile

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.Assert.*
import org.junit.runner.RunWith
import org.json.JSONArray
import kotlin.math.sqrt

@RunWith(AndroidJUnit4::class)
class PhoneModelTest {
    @Test fun indexOpensAndListsSelectedRoots() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        PhoneIndex(context).use { index -> assertNotNull(index.roots()) }
    }
    @Test fun englishTokenizerAndVectorsMatchDesktopReference() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val references = JSONArray(instrumentation.context.assets.open("desktop-reference.json").bufferedReader().use { it.readText() })
        PhoneEmbedder(instrumentation.targetContext).use { model ->
            for (row in 0 until references.length()) {
                val reference = references.getJSONObject(row)
                val text = reference.getString("text")
                val tokens = reference.getJSONArray("tokens")
                assertArrayEquals(LongArray(tokens.length()) { tokens.getLong(it) }, model.tokens(text))
                val actual = model.embed(text)
                val expected = reference.getJSONArray("vector")
                assertEquals(384, actual.size)
                val dot = actual.indices.sumOf { actual[it].toDouble() * expected.getDouble(it) }
                val norm = sqrt(actual.sumOf { it.toDouble() * it })
                assertEquals(1.0, norm, .0001)
                assertTrue("ONNX conversion parity", dot > .999)
            }
            val document = model.embed("Rental deposit returned thirty days after moving out.")
            val query = model.embed("How soon do I get my rental deposit after leaving?")
            val distractor = model.embed("Physics laboratory is scheduled on Wednesday.")
            fun similarity(a: FloatArray, b: FloatArray) = a.indices.sumOf { a[it].toDouble() * b[it] }
            assertTrue(similarity(query, document) > similarity(query, distractor))
        }
    }
}
