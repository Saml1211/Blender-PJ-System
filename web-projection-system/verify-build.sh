#!/bin/bash

# Run TypeScript compiler to check for errors
echo "Running TypeScript compiler check..."
npx tsc --noEmit

# If the TypeScript check passes, try to build the application
if [ $? -eq 0 ]; then
  echo "TypeScript check passed. Building application..."
  npm run build
  
  if [ $? -eq 0 ]; then
    echo "Build successful! The application can be built without errors."
  else
    echo "Build failed. Please check the error messages above."
  fi
else
  echo "TypeScript check failed. Please fix the errors before building."
fi
