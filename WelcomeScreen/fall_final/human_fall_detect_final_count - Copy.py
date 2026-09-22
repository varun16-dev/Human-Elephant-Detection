import cv2
thres = 0.45
cap = cv2.VideoCapture(0)
cap.set(3,1280)
cap.set(4,720)
cap.set(10,70)

j=0

classNames= []
classFile = 'coco.data'
with open(classFile,'rt') as f:
    classNames = f.read().rstrip('\n').split('\n')

configPath = 'ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt.txt'
weightsPath = 'frozen_inference_graph.pb'
net = cv2.dnn_DetectionModel(weightsPath,configPath)
net.setInputSize(320,320)
net.setInputScale(1.0/ 127.5)
net.setInputMean((127.5, 127.5, 127.5))
net.setInputSwapRB(True)

while True:
    success,img = cap.read()
    classIds, confs, bbox = net.detect(img,confThreshold=0.45)
    a = 0
    if len(classIds) != 0:
        for classId, confidence,box in zip(classIds.flatten(),confs.flatten(),bbox):
            object_name=(classNames[classId-1])
            object_id=[classId-1]

            if object_id ==[0]:
                a=a+1
                print(a)

                for (x, y, w, h) in bbox:

                        if h < w:
                            j += 1

                        if j > 10:
                            print("FALL")
                            cv2.putText(img, 'FALL', (x, y), cv2.FONT_HERSHEY_TRIPLEX, 1, (0, 0, 255), 2)
                            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)

                        if h > w:
                            j = 0
                            print("STAND")
                            cv2.putText(img, 'stand', (x, y), cv2.FONT_HERSHEY_TRIPLEX, 1, (255,0, 0), 2)
                            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)

    cv2.imshow("Output",img)
    cv2.waitKey(1)