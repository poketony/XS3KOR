import noesis
import rapi

def registerNoesisTypes():
	handle = noesis.register("Xenosaga XTX Texture", ".xtx")
	noesis.setHandlerTypeCheck(handle, xtxCheckType)
	noesis.setHandlerLoadRGBA(handle, xtxGetRGBA)
	return 1
	
XTX_TAG = 0x00585458 # XTX.
	
def xtxCheckType(data):
	if len(data) &lt; 0x50:
		return 0
	bs = NoeBitStream(data)

	if bs.readInt() != XTX_TAG:
		return 0
		
	return 1

def xtxGetRGBA(data, texList):
	bs = NoeBitStream(data)
	
	#tag
	bs.readInt()
	#start of pixels
	imageOffset = int(bs.readByte())
	
	#unknown
	bs.readBytes(11)
	
	#width
	w = int(bs.readUShort())
	#swizzel indicator...?
	swiz = int(bs.readUShort())
	#height
	h = int(bs.readUShort())
	
	imgPix = data[imageOffset:]
	
	if (swiz != 0x04):
		return 0
	
	#This next loop takes care of the half size alpha channel. The files max alpha at 0x80 instead of 0xFF
	#this is here to spread the values so they max at 0xFF for fully opaque
	#if there is a better way to do this, let me know.
	
	for i in range(0,w*h):
		if imgPix[((i+1)*4)-1] &gt; 0:
			imgPix[((i+1)*4)-1] = ((imgPix[((i+1)*4)-1] * 2)-1)&amp;0xFF
	
	pix32 = rapi.imageDecodeRaw(imgPix, w, h, "r8g8b8a8")
	
	texList.append(NoeTexture("xtx", w, h, pix32, noesis.NOESISTEX_RGBA32))
	return 1