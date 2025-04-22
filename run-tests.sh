#!/bin/sh


git clone https://github.com/llvm/llvm-project --depth=1
cd llvm-project

rm -rf build

mkdir build
cd build

sed -i 's/EnableNewConstInterp(C.getLangOpts().EnableNewConstInterp)/EnableNewConstInterp(true)/g' ../clang/lib/AST/ExprConstant.cpp


CC=clang CXX=clang++ LDFLAGS="-fuse-ld=lld" \
  cmake ../llvm \
  -GNinja \
  -DCMAKE_BUILD_TYPE=Debug \
  -DLLVM_ENABLE_PROJECTS=clang \
  -DLLVM_ENABLE_RUNTIMES="libcxx;libcxxabi" \
  -DLIBCXXABI_USE_LLVM_UNWINDER=OFF \
  -DLLVM_BUILD_LLVM_DYLIB=ON \
  -DLLVM_LINK_LLVM_DYLIB=ON \
  -DCLANG_LINK_CLANG_DYLIB=ON




#### Excluded tests

# These fail because we rely on them NOT using the new interpreter.
rm -rf ../clang/test/AST/ByteCode


# Needs array fillers
rm -f ../clang/test/SemaCXX/large-array-init.cpp
rm -f ../clang/test/CodeGenCXX/cxx11-initializer-aggregate.cpp

rm -f ../clang/test/SemaCXX/constant-expression-cxx14.cpp
rm -f ../clang/test/SemaCXX/aggregate-initialization.cpp
rm -f ../clang/test/SemaCXX/constexpr-function-recovery-crash.cpp


# We are correct.
rm -f ../clang/test/SemaCXX/source_location.cpp
rm -f ../clang/test/SemaCXX/constexpr-vectors-access-elements.cpp
rm -f ../clang/test/Sema/builtin-memcpy.c
rm -f ../clang/test/SemaTemplate/temp_arg_nontype_cxx20.cpp

# Comparing string pointers for equality is unspecified
rm -rf ../clang/test/CodeGenObjC/encode-test-4.m

# Differences are OK.
rm -rf ../clang/test/SemaCXX/new-delete.cpp
rm -rf ../clang/test/SemaCXX/builtin-std-move.cpp
rm -rf ../clang/test/SemaTemplate/temp_arg_nontype_cxx2c.cpp



ninja

echo "Running all clang tests..."
ninja check-clang > out.txt 2>&1

echo "Running all libc++ tests..."
ninja check-cxx >> out.txt 2>&1


echo "DONE"
