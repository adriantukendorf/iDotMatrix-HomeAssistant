#!/bin/bash
# Resize GIFs to 64x64 and optimize to under a target size (default 128KB)
# Requires: gifsicle and ImageMagick (convert for resize, gifsicle for optimization)

TARGET_SIZE=${1:-131072}  # 128KB in bytes
INPUT_DIR="${2:-.}"
OUTPUT_DIR="${3:-$INPUT_DIR/optimized}"
DIMENSIONS="64x64"

mkdir -p "$OUTPUT_DIR"

find "$INPUT_DIR" -maxdepth 1 -type f \( -iname "*.gif" \) -print0 | while IFS= read -r -d '' gif; do
    filename=$(basename "$gif")
    filesize=$(stat -f%z "$gif" 2>/dev/null || stat -c%s "$gif" 2>/dev/null)
    outfile="$OUTPUT_DIR/$filename"

    echo "PROCESSING: $filename (${filesize} bytes)"

    # First resize to 64x64 using ImageMagick (handles animation properly)
    convert "$gif" -coalesce -resize ${DIMENSIONS}! -layers Optimize "$outfile" 2>/dev/null

    if [ ! -f "$outfile" ]; then
        echo "  ERROR: Failed to create output file"
        continue
    fi

    # Now optimize with gifsicle
    gifsicle -O3 "$outfile" -o "$outfile" 2>/dev/null

    newsize=$(stat -f%z "$outfile" 2>/dev/null || stat -c%s "$outfile" 2>/dev/null)

    if [ -n "$newsize" ] && [ "$newsize" -le "$TARGET_SIZE" ]; then
        echo "  -> ${newsize} bytes - done"
        continue
    fi

    echo "  -> ${newsize} bytes, optimizing further..."

    # Try increasingly aggressive lossy compression
    for lossy in 30 60 90 120 150 200; do
        gifsicle -O3 --lossy=$lossy "$outfile" -o "$outfile" 2>/dev/null

        newsize=$(stat -f%z "$outfile" 2>/dev/null || stat -c%s "$outfile" 2>/dev/null)

        if [ -n "$newsize" ] && [ "$newsize" -le "$TARGET_SIZE" ]; then
            echo "  -> Reduced to ${newsize} bytes (lossy=$lossy)"
            break
        fi
    done

    # If still too big, also reduce colors
    newsize=$(stat -f%z "$outfile" 2>/dev/null || stat -c%s "$outfile" 2>/dev/null)
    if [ -z "$newsize" ] || [ "$newsize" -gt "$TARGET_SIZE" ]; then
        for colors in 64 32 16; do
            gifsicle -O3 --lossy=200 --colors $colors "$outfile" -o "$outfile" 2>/dev/null

            newsize=$(stat -f%z "$outfile" 2>/dev/null || stat -c%s "$outfile" 2>/dev/null)

            if [ -n "$newsize" ] && [ "$newsize" -le "$TARGET_SIZE" ]; then
                echo "  -> Reduced to ${newsize} bytes (lossy=200, colors=$colors)"
                break
            fi
        done
    fi

    # Final check
    newsize=$(stat -f%z "$outfile" 2>/dev/null || stat -c%s "$outfile" 2>/dev/null)
    if [ -z "$newsize" ]; then
        echo "  ERROR: Failed to process file"
    elif [ "$newsize" -gt "$TARGET_SIZE" ]; then
        echo "  WARNING: Could not reduce below target (final: ${newsize} bytes)"
    fi
done

echo ""
echo "Done! Optimized 64x64 GIFs are in: $OUTPUT_DIR"
