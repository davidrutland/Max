// Prepares an image for the model. For text-dense images (documents/reports) resolution is
// critical — downscaling too far or JPEG artefacts make the model unable to read the digits and
// it MAKES THEM UP instead. So images within maxDim are sent ORIGINAL (lossless, source format),
// like OpenWebUI does; only oversized ones are scaled down, and then a PNG source stays PNG
// (lossless) while photos become high-quality JPEG.
export function fileToScaledDataUrl(file, maxDim = 768) {
  console.log(`[VISION] fileToScaledDataUrl called: ${file.name} ${file.type} ${file.size} bytes maxDim=${maxDim}`);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      const original = reader.result; // original bytes, source format (lossless)
      const img = new Image();
      img.onerror = reject;
      img.onload = () => {
        const originalW = img.width;
        const originalH = img.height;

        if (Math.max(originalW, originalH) <= maxDim) {
          console.log(
            `[VISION] image unchanged: ${originalW}x${originalH} -> ${originalW}x${originalH}`
          );
          resolve(original);
          return;
        }

        const scale = maxDim / Math.max(originalW, originalH);
        const w = Math.round(originalW * scale);
        const h = Math.round(originalH * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        const type = file.type === "image/png" ? "image/png" : "image/jpeg";
        const output = canvas.toDataURL(type, 0.92);

        console.log(
          `[VISION] image scaled: ${originalW}x${originalH} -> ${w}x${h} (${type})`
        );

        resolve(output);
      };
      img.src = original;
    };
    reader.readAsDataURL(file);
  });
}
