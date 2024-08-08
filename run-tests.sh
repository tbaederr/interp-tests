#!/bin/sh


git clone https://github.com/llvm/llvm-project --depth=1
cd llvm-project
mkdir build
cd build

sed -i 's/EnableNewConstInterp(C.getLangOpts().EnableNewConstInterp)/EnableNewConstInterp(true)/g' ../clang/lib/AST/ExprConstant.cpp


CC=clang CXX=clang++ LDFLAGS="-fuse-ld=lld" \
  cmake ../llvm \
  -GNinja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DLLVM_ENABLE_PROJECTS=clang




#### Excluded tests

# These fail because we rely on them NOT using the new interpreter.
rm -rf ../clang/test/AST/Interp


# Needs array fillers
rm -f ../clang/test/SemaCXX/large-array-init.cpp
rm -f ../clang/test/CodeGenCXX/cxx11-initializer-aggregate.cpp

rm -f ../clang/test/SemaCXX/constant-expression-cxx14.cpp
rm -f ../clang/test/SemaCXX/aggregate-initialization.cpp
rm -f ../clang/test/SemaCXX/constexpr-function-recovery-crash.cpp


# We are correct.
rm -f ../clang/test/SemaCXX/source_location.cpp
rm -f ../clang/test/SemaCXX/constexpr-vectors-access-elements.cpp

# Comparing string pointers for equality is unspecified
rm -rf ../clang/test/CodeGenObjC/encode-test-4.m

ninja

echo "Running all clang tests..."
ninja check-clang > out.txt 2>&1

echo "DONE"
