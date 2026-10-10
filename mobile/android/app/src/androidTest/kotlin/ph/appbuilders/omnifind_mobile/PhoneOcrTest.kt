package ph.appbuilders.omnifind_mobile

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream

@RunWith(AndroidJUnit4::class)
class PhoneOcrTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun image(format: Bitmap.CompressFormat, blank: Boolean = false, width: Int = 1280, height: Int = 720): ByteArray {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        try {
            val canvas = Canvas(bitmap)
            canvas.drawColor(Color.WHITE)
            if (!blank) {
                val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 42f; typeface = Typeface.DEFAULT }
                canvas.drawText("Rental deposit returned after moving out.", 60f, 120f, paint)
                canvas.drawText("Reference PKG-483", 60f, 210f, paint)
                canvas.drawText("Physics laboratory on Wednesday.", 60f, 300f, paint)
            }
            return ByteArrayOutputStream().also { assertTrue(bitmap.compress(format, 95, it)) }.toByteArray()
        } finally { bitmap.recycle() }
    }
    private fun rejected(expected: String, action: () -> Unit) {
        try { action(); fail("Expected $expected") } catch (error: IllegalArgumentException) { assertEquals(expected, error.message) }
    }
    @Test fun pngRecognizesWordsCodeAndOriginalPixelRegions() {
        PhoneTextExtractor(context).use { extractor ->
            val lines = extractor.extract("screenshot.png", image(Bitmap.CompressFormat.PNG)) {}
            val text = lines.joinToString(" ") { it.text }
            assertTrue(text.contains("Rental deposit"))
            assertTrue(text.contains("PKG-483"))
            for (line in lines) {
                assertEquals("ocr", line.kind)
                assertNull(line.page)
                val box = line.region!!
                assertEquals(4, box.size)
                assertTrue(box[0] >= 0 && box[1] >= 0 && box[2] <= 1280 && box[3] <= 720)
                assertTrue(box[2] > box[0] && box[3] > box[1])
            }
            PhoneEmbedder(context).use { model ->
                val query = model.embed("How soon do I get my rental deposit after leaving?")
                fun score(text: String): Double { val vector = model.embed(text); return vector.indices.sumOf { query[it].toDouble() * vector[it] } }
                assertTrue(score(lines.first { it.text.contains("Rental") }.text) > score(lines.first { it.text.contains("Physics") }.text))
            }
        }
    }
    @Test fun uprightJpegRecognizesText() {
        PhoneTextExtractor(context).use { extractor ->
            assertTrue(extractor.extract("screenshot.JPG", image(Bitmap.CompressFormat.JPEG)) {}.any { it.text.contains("PKG-483") })
        }
    }
    @Test fun emptyAndMalformedImagesHaveExplicitIssues() {
        PhoneTextExtractor(context).use { extractor ->
            rejected("image-no-text") { extractor.extract("blank.png", image(Bitmap.CompressFormat.PNG, blank = true)) {} }
            rejected("image-unreadable") { extractor.extract("broken.png", "not an image".toByteArray()) {} }
        }
    }
    @Test fun imagePixelBoundIsCheckedBeforeOcr() {
        PhoneTextExtractor(context).use { extractor ->
            rejected("image-pixel-limit") { extractor.extract("large.png", image(Bitmap.CompressFormat.PNG, blank = true, width = 3000, height = 2000)) {} }
        }
    }
    @Test fun cancellationDoesNotReturnPartialImageEvidence() {
        PhoneTextExtractor(context).use { extractor ->
            var checkpoints = 0
            try {
                extractor.extract("cancel.png", image(Bitmap.CompressFormat.PNG)) { if (++checkpoints == 4) error("indexing-cancelled") }
                fail("Expected cancellation")
            } catch (error: IllegalStateException) { assertEquals("indexing-cancelled", error.message) }
        }
    }
}
