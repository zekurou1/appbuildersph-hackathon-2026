package ph.appbuilders.omnifind_mobile

import android.content.Context
import android.graphics.BitmapFactory
import android.media.ExifInterface
import com.googlecode.tesseract.android.TessBaseAPI
import java.io.ByteArrayInputStream
import java.io.File

/** English upright screenshots only; original bytes and pixels are never persisted here. */
class PhoneOcr(private val context: Context) : AutoCloseable {
    companion object {
        const val MODEL_SHA = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
        fun validateSize(width: Int, height: Int) {
            require(width > 0 && height > 0) { "image-unreadable" }
            require(width.toLong() * height <= 4_000_000L) { "image-pixel-limit" }
        }
    }
    private var api: TessBaseAPI? = null
    private fun engine(): TessBaseAPI {
        api?.let { return it }
        val directory = File(context.filesDir, "ocr/tessdata").apply { mkdirs() }
        val data = File(directory, "eng.traineddata")
        if (!data.exists() || PhoneIndex.digest(data.readBytes()) != MODEL_SHA) {
            val bytes = context.assets.open("eng.traineddata").use { it.readBytes() }
            require(PhoneIndex.digest(bytes) == MODEL_SHA) { "ocr-model-invalid" }
            data.writeBytes(bytes)
        }
        val created = TessBaseAPI()
        try {
            require(created.init(directory.parentFile!!.absolutePath + "/", "eng", TessBaseAPI.OEM_LSTM_ONLY)) { "ocr-model-invalid" }
            created.setPageSegMode(TessBaseAPI.PageSegMode.PSM_SPARSE_TEXT)
            api = created
            return created
        } catch (error: Exception) { created.recycle(); throw error }
    }
    fun extract(bytes: ByteArray, checkpoint: () -> Unit): List<SourceLine> {
        checkpoint()
        require(bytes.size <= 1_048_576) { "file-too-large" }
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
        require(options.outMimeType in setOf("image/png", "image/jpeg")) { "image-unreadable" }
        validateSize(options.outWidth, options.outHeight)
        if (options.outMimeType == "image/jpeg") {
            val orientation = ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            require(orientation == ExifInterface.ORIENTATION_NORMAL || orientation == ExifInterface.ORIENTATION_UNDEFINED) { "image-needs-rotation" }
        }
        checkpoint()
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: error("image-unreadable")
        try {
            val tess = engine()
            try {
                tess.setImage(bitmap)
                val text = tess.getUTF8Text().orEmpty()
                checkpoint()
                require(text.length <= 100_000) { "ocr-text-limit" }
                require(text.isNotBlank()) { "image-no-text" }
                val iterator = tess.resultIterator ?: error("image-no-text")
                try {
                    iterator.begin()
                    val lines = mutableListOf<SourceLine>()
                    do {
                        checkpoint()
                        val line = iterator.getUTF8Text(TessBaseAPI.PageIteratorLevel.RIL_TEXTLINE).orEmpty().trim()
                        if (line.isNotBlank()) {
                            require(lines.size < 2000) { "passage-count-limit" }
                            val region = iterator.getBoundingBox(TessBaseAPI.PageIteratorLevel.RIL_TEXTLINE).toList()
                            lines.add(SourceLine(null, lines.size + 1, line, "ocr", region))
                        }
                    } while (iterator.next(TessBaseAPI.PageIteratorLevel.RIL_TEXTLINE))
                    require(lines.isNotEmpty()) { "image-no-text" }
                    return lines
                } finally { iterator.delete() }
            } finally { tess.clear() }
        } finally { bitmap.recycle() }
    }
    override fun close() { api?.recycle(); api = null }
}
