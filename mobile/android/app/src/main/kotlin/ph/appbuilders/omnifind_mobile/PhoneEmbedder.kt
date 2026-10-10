package ph.appbuilders.omnifind_mobile

import android.content.Context
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.LongBuffer
import java.text.Normalizer
import java.util.Locale
import kotlin.math.sqrt

/** CPU-only bundled model. No server, runtime download or generative answers. */
class PhoneEmbedder(context: Context) : AutoCloseable {
    private val env = OrtEnvironment.getEnvironment()
    private val vocab = context.assets.open("vocab.txt").bufferedReader().use { it.readLines() }
        .withIndex().associate { it.value to it.index.toLong() }
    private val session: OrtSession
    init {
        env.setTelemetry(false)
        val bytes = context.assets.open("model.onnx").use { it.readBytes() }
        check(PhoneIndex.digest(bytes) == "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452")
        OrtSession.SessionOptions().use { options ->
            options.setIntraOpNumThreads(2)
            session = env.createSession(bytes, options)
        }
    }
    fun tokens(text: String): LongArray {
        val clean = Normalizer.normalize(text.lowercase(Locale.ROOT), Normalizer.Form.NFD)
            .replace(Regex("\\p{M}"), "").replace(Regex("[\\p{Cc}\\p{Cf}]"), " ")
        val words = Regex("[\\p{L}\\p{N}]+|[^\\s\\p{L}\\p{N}]").findAll(clean).map { it.value }
        val pieces = mutableListOf<Long>()
        for (word in words) {
            if (word.length > 100) { pieces.add(vocab.getValue("[UNK]")); continue }
            var start = 0
            val partial = mutableListOf<Long>()
            while (start < word.length) {
                var end = word.length
                var found: Long? = null
                while (end > start) {
                    found = vocab[(if (start == 0) "" else "##") + word.substring(start, end)]
                    if (found != null) break
                    end--
                }
                if (found == null) { partial.clear(); partial.add(vocab.getValue("[UNK]")); break }
                partial.add(found); start = end
            }
            pieces.addAll(partial)
        }
        require(pieces.size <= 254) { "query-too-long" }
        return (listOf(vocab.getValue("[CLS]")) + pieces + vocab.getValue("[SEP]")).toLongArray()
    }
    fun embed(text: String): FloatArray {
        val ids = tokens(text)
        val shape = longArrayOf(1, ids.size.toLong())
        OnnxTensor.createTensor(env, LongBuffer.wrap(ids), shape).use { input ->
            OnnxTensor.createTensor(env, LongBuffer.wrap(LongArray(ids.size) { 1 }), shape).use { mask ->
                OnnxTensor.createTensor(env, LongBuffer.wrap(LongArray(ids.size)), shape).use { types ->
                    session.run(mapOf("input_ids" to input, "attention_mask" to mask, "token_type_ids" to types)).use { result ->
                        @Suppress("UNCHECKED_CAST")
                        val hidden = (result[0].value as Array<Array<FloatArray>>)[0]
                        val vector = FloatArray(384)
                        for (token in hidden) for (i in vector.indices) vector[i] += token[i] / hidden.size
                        val norm = sqrt(vector.sumOf { it.toDouble() * it })
                        check(norm.isFinite() && norm > 0)
                        return FloatArray(384) { (vector[it] / norm).toFloat() }
                    }
                }
            }
        }
    }
    override fun close() = session.close()
}
