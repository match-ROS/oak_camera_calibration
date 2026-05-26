#!/usr/bin/env python3
import rospy
import tf

rospy.init_node("tf_test")

listener = tf.TransformListener()
rospy.sleep(1.0)  # wichtig: TF-Buffer füllen

try:
    (trans, rot) = listener.lookupTransform("base_link", "tool0", rospy.Time(0))
    print("Translation:", trans)
    print("Rotation (quat):", rot)
except Exception as e:
    print("TF error:", e)
