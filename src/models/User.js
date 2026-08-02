import mongoose from "mongoose"

const userSchema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: true,
      trim: true,
    },
    username: {
      type: String,
      required: true,
      trim: true,
    },
    usernameKey: {
      type: String,
      required: true,
      unique: true,
      sparse: true,
    },
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
    },
    passwordHash: {
      type: String,
      required: true,
      select: false,
    },
    sessionVersion: {
      type: Number,
      default: 0,
      required: true,
    },
  },
  { timestamps: true }
)

userSchema.set("toJSON", {
  transform: (_document, result) => {
    delete result.passwordHash
    delete result.sessionVersion
    delete result.usernameKey
    delete result.__v
    return result
  },
})

const User = mongoose.models.User || mongoose.model("User", userSchema)

export default User
