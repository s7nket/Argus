import React from 'react';
import { RouterProvider } from 'react-router';
import { router } from './routes';
import { MotionConfig } from 'motion/react';

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <RouterProvider router={router} />
    </MotionConfig>
  );
}
