/* Minimal QuartzCore surface for headers this mode compiles (no-xcode mode).
   Written for this repo; the framework itself comes from the device. */
#ifndef QUARTZCORE_MINIMAL_H
#define QUARTZCORE_MINIMAL_H

#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>

typedef struct CATransform3D {
  CGFloat m11, m12, m13, m14;
  CGFloat m21, m22, m23, m24;
  CGFloat m31, m32, m33, m34;
  CGFloat m41, m42, m43, m44;
} CATransform3D;

extern const CATransform3D CATransform3DIdentity;

@class CALayer;
@class CADisplayLink;

#endif
