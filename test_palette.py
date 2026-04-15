from PIL import Image
try:
    img = Image.new("RGB", (100, 100), color="red")
    img.paste(Image.new("RGB", (50, 50), color="blue"), (0, 0))
    q = img.quantize(colors=5, kmeans=3)
    p = q.getpalette()[:15]
    colors = [(p[i], p[i+1], p[i+2]) for i in range(0, len(p), 3)]
    print(colors)
except Exception as e:
    print(e)
